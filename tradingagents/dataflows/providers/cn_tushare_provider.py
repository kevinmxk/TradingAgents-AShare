from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import pandas as pd
from stockstats import wrap

from .base import BaseMarketDataProvider
from ..trade_calendar import cn_no_data_reason


CAPABILITY_STATUSES = {
    "available",
    "permission_denied",
    "rate_limited",
    "invalid_token",
    "empty_result",
    "network_error",
    "server_error",
    "unknown_error",
    "not_configured",
    "not_supported_first_version",
}


class TushareProviderError(RuntimeError):
    def __init__(self, status: str, message: str):
        self.status = status if status in CAPABILITY_STATUSES else "unknown_error"
        super().__init__(message)


def normalize_to_ts_code(ticker: str) -> str:
    s = str(ticker or "").strip().upper()
    if not s:
        raise NotImplementedError("cn_tushare requires a non-empty A-share symbol")

    compact = s.replace("-", ".").replace("_", ".")
    m = re.fullmatch(r"(\d{6})\.(SH|SZ|BJ)", compact)
    if m:
        return f"{m.group(1)}.{m.group(2)}"

    m = re.fullmatch(r"(SH|SZ|BJ)\.?(\d{6})", compact)
    if m:
        return f"{m.group(2)}.{m.group(1)}"

    m = re.search(r"(\d{6})", compact)
    if not m:
        raise NotImplementedError(f"cn_tushare only supports A-share 6-digit symbols, got: {ticker}")

    code = m.group(1)
    if code.startswith("6"):
        suffix = "SH"
    elif code.startswith(("0", "3")):
        suffix = "SZ"
    elif code.startswith(("4", "8", "9")):
        suffix = "BJ"
    else:
        raise NotImplementedError(f"cn_tushare cannot infer exchange for symbol: {ticker}")
    return f"{code}.{suffix}"


def to_tushare_date(value: str | datetime | None) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y%m%d")
    text = str(value).strip()
    if not text:
        return ""
    if re.fullmatch(r"\d{8}", text):
        return text
    parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        raise ValueError(f"Invalid date for Tushare: {value}")
    return pd.to_datetime(parsed).strftime("%Y%m%d")


def classify_tushare_error(exc: BaseException | str) -> str:
    detail = str(exc or "").strip()
    lowered = detail.lower()
    if not detail:
        return "unknown_error"

    token_markers = (
        "40101",
        "40102",
        "invalid token",
        "incorrect token",
        "token invalid",
        "token incorrect",
        "token is invalid",
        "token不存在",
        "token错误",
        "token不对",
        "无效token",
        "token无效",
        "错误的token",
    )
    if any(marker in lowered for marker in token_markers):
        return "invalid_token"
    if "token" in lowered and any(x in lowered for x in ("invalid", "incorrect", "wrong", "error")):
        return "invalid_token"

    permission_markers = (
        "2002",
        "权限",
        "积分",
        "抱歉",
        "permission",
        "privilege",
        "not allowed",
        "no access",
    )
    if any(marker in lowered for marker in permission_markers):
        return "permission_denied"

    rate_markers = ("每分钟", "频次", "限流", "rate", "limit", "too many")
    if any(marker in lowered for marker in rate_markers):
        return "rate_limited"
    if any(x in lowered for x in ("timeout", "timed out", "connection", "network", "proxy", "dns")):
        return "network_error"
    if "500" in lowered or "502" in lowered or "503" in lowered or "504" in lowered:
        return "server_error"
    return "unknown_error"


class CnTushareProvider(BaseMarketDataProvider):
    """A-share structured data provider backed by Tushare Pro.

    The first version uses Tushare ``daily`` prices, which are unadjusted
    OHLCV bars. Technical indicators computed here therefore use unadjusted
    price history unless an adjusted-data path is enabled explicitly later.
    """

    INDICATOR_DESCRIPTIONS = {
        "close_50_sma": "50-day simple moving average.",
        "close_200_sma": "200-day simple moving average.",
        "close_10_ema": "10-day exponential moving average.",
        "macd": "MACD trend and momentum indicator.",
        "macds": "MACD signal line.",
        "macdh": "MACD histogram.",
        "rsi": "Relative Strength Index.",
        "boll": "Bollinger middle band.",
        "boll_ub": "Bollinger upper band.",
        "boll_lb": "Bollinger lower band.",
        "atr": "Average True Range.",
        "vwma": "Volume weighted moving average.",
        "mfi": "Money Flow Index.",
    }

    PROBE_SPECS: Dict[str, Dict[str, Any]] = {
        "daily": {
            "params": {"ts_code": "600519.SH", "start_date": "20240102", "end_date": "20240102"},
            "fields": "ts_code,trade_date,open,high,low,close,vol,amount",
        },
        "stock_basic": {
            "params": {"exchange": "", "list_status": "L"},
            "fields": "ts_code,symbol,name,area,industry,list_date",
        },
        "trade_cal": {
            "params": {"exchange": "SSE", "start_date": "20240102", "end_date": "20240102"},
            "fields": "exchange,cal_date,is_open",
        },
        "adj_factor": {
            "params": {"ts_code": "600519.SH", "trade_date": "20240102"},
            "fields": "ts_code,trade_date,adj_factor",
        },
        "daily_basic": {
            "params": {"ts_code": "600519.SH", "trade_date": "20240102"},
            "fields": "ts_code,trade_date,turnover_rate,pe,pb,total_mv,circ_mv",
        },
        "fina_indicator": {
            "params": {"ts_code": "600519.SH", "period": "20231231"},
            "fields": "ts_code,end_date,roe,roa,grossprofit_margin,netprofit_margin",
        },
        "income": {
            "params": {"ts_code": "600519.SH", "period": "20231231"},
            "fields": "ts_code,end_date,revenue,n_income",
        },
        "balancesheet": {
            "params": {"ts_code": "600519.SH", "period": "20231231"},
            "fields": "ts_code,end_date,total_assets,total_liab,total_hldr_eqy_exc_min_int",
        },
        "cashflow": {
            "params": {"ts_code": "600519.SH", "period": "20231231"},
            "fields": "ts_code,end_date,n_cashflow_act,n_cashflow_inv_act,n_cash_flows_fnc_act",
        },
    }

    _cache: Dict[str, tuple[float, pd.DataFrame]] = {}
    _rate_lock = threading.Lock()
    _call_timestamps: list[float] = []

    @property
    def name(self) -> str:
        return "cn_tushare"

    def _cfg(self, key: str, default: Any = None) -> Any:
        try:
            from tradingagents.dataflows.config import get_config

            value = get_config().get(key)
            if value not in (None, ""):
                return value
        except Exception:
            pass
        return default

    def _settings(self) -> Dict[str, Any]:
        return {
            "enabled": bool(self._cfg("tushare_enabled", False)),
            "token": str(self._cfg("tushare_token", "") or "").strip(),
            "proxy_url": str(self._cfg("tushare_proxy_url", "") or "").strip(),
            "timeout": int(self._cfg("tushare_timeout", 10) or 10),
            "rate_limit_per_minute": int(self._cfg("tushare_rate_limit_per_minute", 40) or 40),
            "cache_ttl_seconds": int(self._cfg("tushare_cache_ttl_seconds", 86400) or 86400),
            "capabilities": self._cfg("tushare_capabilities", {}) or {},
        }

    def _ensure_available(self, api_name: str = "daily") -> Dict[str, Any]:
        settings = self._settings()
        if not settings["enabled"]:
            raise NotImplementedError("cn_tushare is disabled")
        if not settings["token"]:
            raise NotImplementedError("cn_tushare token is not configured")
        status = (settings.get("capabilities") or {}).get(api_name)
        if status and status != "available":
            raise NotImplementedError(f"cn_tushare {api_name} capability is {status}")
        return settings

    @classmethod
    def _pro(cls, token: str):
        try:
            import tushare as ts  # type: ignore
        except ImportError as exc:
            raise TushareProviderError(
                "unknown_error",
                "cn_tushare requires 'tushare'. Install it with: pip install tushare",
            ) from exc
        return ts.pro_api(token)

    @classmethod
    def _rate_limit(cls, per_minute: int) -> None:
        per_minute = max(1, int(per_minute or 40))
        with cls._rate_lock:
            now = time.monotonic()
            cls._call_timestamps = [t for t in cls._call_timestamps if now - t < 60]
            if len(cls._call_timestamps) >= per_minute:
                wait_for = 60 - (now - cls._call_timestamps[0])
                if wait_for > 0:
                    time.sleep(min(wait_for, 3))
            cls._call_timestamps.append(time.monotonic())

    @classmethod
    def call_api(
        cls,
        token: str,
        api_name: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        fields: Optional[str] = None,
        rate_limit_per_minute: int = 40,
        timeout: int = 10,
        proxy_url: Optional[str] = None,
    ) -> pd.DataFrame:
        token = str(token or "").strip()
        if not token:
            raise TushareProviderError("not_configured", "Tushare token is not configured")
        cls._rate_limit(rate_limit_per_minute)
        try:
            import requests

            endpoint = (proxy_url or "").strip() or "http://api.tushare.pro"
            response = requests.post(
                endpoint,
                json={
                    "api_name": api_name,
                    "token": token,
                    "params": params or {},
                    "fields": fields or "",
                },
                timeout=timeout,
            )
            response.raise_for_status()
            payload = response.json()
            code = payload.get("code")
            if code != 0:
                msg = str(payload.get("msg") or payload.get("message") or "")
                if code in (40101, 40102):
                    raise TushareProviderError("invalid_token", msg or "Tushare token is invalid")
                if code == 2002:
                    raise TushareProviderError("permission_denied", msg or "Tushare permission denied")
                raise TushareProviderError(classify_tushare_error(f"{code} {msg}"), msg or f"Tushare code={code}")
            data = payload.get("data") or {}
            items = data.get("items") or []
            columns = data.get("fields") or []
            df = pd.DataFrame(items, columns=columns)
        except TushareProviderError:
            raise
        except Exception as exc:
            raise TushareProviderError(classify_tushare_error(exc), str(exc)[:300]) from exc
        return df

    @classmethod
    def test_connection(
        cls,
        token: str,
        *,
        rate_limit_per_minute: int = 40,
        timeout: int = 10,
        proxy_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            df = cls.call_api(
                token,
                "daily",
                params={"ts_code": "600519.SH", "start_date": "20240102", "end_date": "20240102"},
                fields="ts_code,trade_date,open,high,low,close,vol,amount",
                rate_limit_per_minute=rate_limit_per_minute,
                timeout=timeout,
                proxy_url=proxy_url,
            )
            return {
                "success": not df.empty,
                "status": "available" if not df.empty else "empty_result",
                "message": "Tushare daily connection succeeded." if not df.empty else "Tushare daily returned no rows.",
                "sample_row_count": int(len(df)),
            }
        except TushareProviderError as exc:
            return {
                "success": False,
                "status": exc.status,
                "message": str(exc),
                "sample_row_count": 0,
            }

    @classmethod
    def probe_capabilities(
        cls,
        token: str,
        *,
        rate_limit_per_minute: int = 40,
        timeout: int = 10,
        proxy_url: Optional[str] = None,
    ) -> Dict[str, str]:
        if not str(token or "").strip():
            result = {name: "not_configured" for name in cls.PROBE_SPECS}
        else:
            result = {}
            for api_name, spec in cls.PROBE_SPECS.items():
                try:
                    df = cls.call_api(
                        token,
                        api_name,
                        params=spec["params"],
                        fields=spec["fields"],
                        rate_limit_per_minute=rate_limit_per_minute,
                        timeout=timeout,
                        proxy_url=proxy_url,
                    )
                    result[api_name] = "available" if not df.empty else "empty_result"
                except TushareProviderError as exc:
                    result[api_name] = exc.status
        result["realtime_quote"] = "not_supported_first_version"
        result["news"] = "not_supported_first_version"
        result["anns"] = "not_supported_first_version"
        return result

    def _cached_api(self, api_name: str, params: Dict[str, Any], fields: str, ttl: int, rate_limit: int) -> pd.DataFrame:
        settings = self._ensure_available(api_name)
        cache_key = json.dumps(
            {
                "api": api_name,
                "params": params,
                "fields": fields,
                "proxy_url": settings.get("proxy_url") or "",
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        now = time.time()
        cached = self._cache.get(cache_key)
        if cached and now - cached[0] < ttl:
            return cached[1].copy()
        try:
            df = self.call_api(
                settings["token"],
                api_name,
                params=params,
                fields=fields,
                rate_limit_per_minute=rate_limit,
                timeout=int(settings["timeout"]),
                proxy_url=str(settings.get("proxy_url") or ""),
            )
        except TushareProviderError as exc:
            raise NotImplementedError(f"cn_tushare {api_name} unavailable: {exc.status}") from exc
        self._cache[cache_key] = (now, df.copy())
        return df

    def _fetch_daily_df(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        settings = self._ensure_available("daily")
        ts_code = normalize_to_ts_code(symbol)
        df = self._cached_api(
            "daily",
            {
                "ts_code": ts_code,
                "start_date": to_tushare_date(start_date),
                "end_date": to_tushare_date(end_date),
            },
            "ts_code,trade_date,open,high,low,close,vol,amount",
            int(settings["cache_ttl_seconds"]),
            int(settings["rate_limit_per_minute"]),
        )
        if df.empty:
            raise NotImplementedError(f"cn_tushare daily returned no rows for {symbol}")
        out = df.rename(
            columns={
                "trade_date": "Date",
                "open": "Open",
                "high": "High",
                "low": "Low",
                "close": "Close",
                "vol": "Volume",
            }
        )
        required = ["Date", "Open", "High", "Low", "Close", "Volume"]
        missing = [c for c in required if c not in out.columns]
        if missing:
            raise NotImplementedError(f"cn_tushare daily missing columns: {missing}")
        out = out[required].copy()
        out["Date"] = pd.to_datetime(out["Date"], format="%Y%m%d", errors="coerce")
        for c in ("Open", "High", "Low", "Close", "Volume"):
            out[c] = pd.to_numeric(out[c], errors="coerce")
        out = out.dropna(subset=required).sort_values("Date").reset_index(drop=True)
        if out.empty:
            raise NotImplementedError(f"cn_tushare daily returned no usable rows for {symbol}")
        return out

    def get_stock_data(self, symbol: str, start_date: str, end_date: str) -> str:
        df = self._fetch_daily_df(symbol, start_date, end_date)
        out = df.copy()
        out["Dividends"] = 0.0
        out["Stock Splits"] = 0.0
        out["Date"] = out["Date"].dt.strftime("%Y-%m-%d")
        header = f"# Stock data for {symbol} from {start_date} to {end_date}\n"
        header += "# Provider: cn_tushare daily (unadjusted OHLCV, not qfq/hfq)\n"
        header += f"# Total records: {len(out)}\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        return header + out.to_csv(index=False)

    def get_indicators(self, symbol: str, indicator: str, curr_date: str, look_back_days: int) -> str:
        if indicator not in self.INDICATOR_DESCRIPTIONS:
            raise ValueError(f"Indicator {indicator} is not supported.")
        curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
        start_dt = curr_dt - timedelta(days=max(look_back_days, 260))
        df = self._fetch_daily_df(symbol, start_dt.strftime("%Y-%m-%d"), curr_date)
        ind_df = df.rename(
            columns={"Date": "date", "Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"}
        )[["date", "open", "high", "low", "close", "volume"]].copy()
        ss = wrap(ind_df)
        series = ss[indicator]
        values_by_date = {}
        for idx, dt_val in enumerate(ind_df["date"]):
            val = series.iloc[idx]
            values_by_date[pd.to_datetime(dt_val).strftime("%Y-%m-%d")] = "N/A" if pd.isna(val) else str(val)
        begin = curr_dt - timedelta(days=look_back_days)
        lines = []
        d = curr_dt
        while d >= begin:
            key = d.strftime("%Y-%m-%d")
            value = values_by_date.get(key) or cn_no_data_reason(key)
            if value == "N/A":
                value = cn_no_data_reason(key)
            lines.append(f"{key}: {value}")
            d -= timedelta(days=1)
        return (
            f"## {indicator} indicator ({begin.strftime('%Y-%m-%d')} to {curr_date})\n\n"
            + "\n".join(lines)
            + "\n\n"
            + "Data basis: cn_tushare daily unadjusted OHLCV (not qfq/hfq).\n\n"
            + self.INDICATOR_DESCRIPTIONS[indicator]
        )

    def _financial_table(self, api_name: str, ticker: str, curr_date: str | None, fields: str, title: str) -> str:
        settings = self._ensure_available(api_name)
        ts_code = normalize_to_ts_code(ticker)
        period = to_tushare_date(curr_date) if curr_date else ""
        if period and not period.endswith(("0331", "0630", "0930", "1231")):
            period = f"{period[:4]}1231"
        params = {"ts_code": ts_code}
        if api_name == "daily_basic":
            params["trade_date"] = to_tushare_date(curr_date) if curr_date else datetime.now().strftime("%Y%m%d")
        elif period:
            params["period"] = period
        df = self._cached_api(
            api_name,
            params,
            fields,
            int(settings["cache_ttl_seconds"]),
            int(settings["rate_limit_per_minute"]),
        )
        if df.empty:
            raise NotImplementedError(f"cn_tushare {api_name} returned no rows")
        return f"## {title} ({ticker})\n\n{df.head(12).to_markdown(index=False)}"

    def get_fundamentals(self, ticker: str, curr_date: str = None) -> str:
        return self._financial_table(
            "daily_basic",
            ticker,
            curr_date,
            "ts_code,trade_date,turnover_rate,pe,pb,total_mv,circ_mv",
            "Tushare Daily Basic",
        )

    def get_balance_sheet(self, ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
        return self._financial_table(
            "balancesheet",
            ticker,
            curr_date,
            "ts_code,end_date,total_assets,total_liab,total_hldr_eqy_exc_min_int",
            "Tushare Balance Sheet",
        )

    def get_cashflow(self, ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
        return self._financial_table(
            "cashflow",
            ticker,
            curr_date,
            "ts_code,end_date,n_cashflow_act,n_cashflow_inv_act,n_cash_flows_fnc_act",
            "Tushare Cashflow",
        )

    def get_income_statement(self, ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
        return self._financial_table(
            "income",
            ticker,
            curr_date,
            "ts_code,end_date,revenue,n_income",
            "Tushare Income Statement",
        )

    def get_news(self, ticker: str, start_date: str, end_date: str) -> str:
        raise NotImplementedError("cn_tushare news is not supported in the first version")

    def get_global_news(self, curr_date: str, look_back_days: int = 7, limit: int = 50) -> str:
        raise NotImplementedError("cn_tushare global news is not supported in the first version")

    def get_insider_transactions(self, symbol: str) -> str:
        raise NotImplementedError("cn_tushare insider transactions are not supported")
