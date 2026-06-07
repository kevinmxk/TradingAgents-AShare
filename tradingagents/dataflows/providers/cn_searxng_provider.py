from __future__ import annotations

import hashlib
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests

from .base import BaseMarketDataProvider

try:
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover - dependency is declared, keep fallback safe.
    BeautifulSoup = None


logger = logging.getLogger(__name__)


TIER0_DOMAINS = (
    "cninfo.com.cn",
    "sse.com.cn",
    "szse.cn",
    "bse.cn",
    "csrc.gov.cn",
    "pbc.gov.cn",
    "stats.gov.cn",
    "ndrc.gov.cn",
    "mof.gov.cn",
)

TIER1_DOMAINS = (
    "stcn.com",
    "cs.com.cn",
    "cnstock.com",
    "cls.cn",
    "yicai.com",
    "xinhuanet.com",
    "people.com.cn",
    "21jingji.com",
    "caixin.com",
)

TIER2_DOMAINS = (
    "eastmoney.com",
    "finance.sina.com.cn",
    "stock.finance.sina.com.cn",
    "finance.qq.com",
    "money.163.com",
    "10jqka.com.cn",
    "hexun.com",
    "jrj.com.cn",
)

TIER3_DOMAINS = (
    "guba.eastmoney.com",
    "xueqiu.com",
    "baijiahao.baidu.com",
    "mp.weixin.qq.com",
    "zhihu.com",
    "bilibili.com",
    "tieba.baidu.com",
)

COMMON_CN_STOCK_NAMES = {
    "000001": "平安银行",
    "000002": "万科A",
    "000063": "中兴通讯",
    "000333": "美的集团",
    "000651": "格力电器",
    "000858": "五粮液",
    "002230": "科大讯飞",
    "002415": "海康威视",
    "002594": "比亚迪",
    "300059": "东方财富",
    "300124": "汇川技术",
    "300308": "中际旭创",
    "300750": "宁德时代",
    "600000": "浦发银行",
    "600030": "中信证券",
    "600036": "招商银行",
    "600050": "中国联通",
    "600519": "贵州茅台",
    "600900": "长江电力",
    "601318": "中国平安",
    "601398": "工商银行",
    "601668": "中国建筑",
    "601888": "中国中免",
    "688981": "中芯国际",
}


@dataclass
class NewsItem:
    title: str
    url: str
    source: str
    snippet: str = ""
    published_at: str | None = None
    body_excerpt: str = ""
    credibility_tier: int = 9
    confidence_score: float = 0.0
    verification_status: str = "unverified"
    engine: str = ""


class CnSearxngProvider(BaseMarketDataProvider):
    """A-share news provider backed by a local SearXNG JSON Search API."""

    @property
    def name(self) -> str:
        return "cn_searxng"

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.base_url = str(
            self._cfg("searxng_base_url", "SEARXNG_BASE_URL", "http://127.0.0.1:8888")
        ).rstrip("/")
        self.mode = str(self._cfg("searxng_mode", "SEARXNG_MODE", "balanced")).lower()
        if self.mode not in {"strict", "balanced", "broad"}:
            self.mode = "balanced"
        self.timeout = float(self._cfg("searxng_timeout", "SEARXNG_TIMEOUT", 8))
        self.fetch_body = self._as_bool(
            self._cfg("searxng_fetch_body", "SEARXNG_FETCH_BODY", True)
        )
        self.max_results = max(
            1, int(self._cfg("searxng_max_results", "SEARXNG_MAX_RESULTS", 16))
        )
        self.min_score = float(self._cfg("searxng_min_score", "SEARXNG_MIN_SCORE", 0.45))
        self.cache_ttl = max(
            0,
            int(self._cfg("searxng_cache_ttl_seconds", "SEARXNG_CACHE_TTL_SECONDS", 900)),
        )
        self.session = requests.Session()
        self._cache: dict[str, tuple[float, list[NewsItem]]] = {}

    def _cfg(self, key: str, env_key: str, default: Any) -> Any:
        if key in self.config:
            return self.config[key]
        try:
            from tradingagents.dataflows.config import get_config

            config_value = get_config().get(key)
            if config_value not in (None, ""):
                return config_value
        except Exception:
            pass
        env_value = os.getenv(env_key)
        if env_value is not None:
            return env_value
        return default

    def _refresh_settings(self) -> None:
        self.base_url = str(
            self._cfg("searxng_base_url", "SEARXNG_BASE_URL", "http://127.0.0.1:8888")
        ).rstrip("/")
        self.mode = str(self._cfg("searxng_mode", "SEARXNG_MODE", "balanced")).lower()
        if self.mode not in {"strict", "balanced", "broad"}:
            self.mode = "balanced"
        self.timeout = float(self._cfg("searxng_timeout", "SEARXNG_TIMEOUT", 8))
        self.fetch_body = self._as_bool(
            self._cfg("searxng_fetch_body", "SEARXNG_FETCH_BODY", True)
        )
        self.max_results = max(
            1, int(self._cfg("searxng_max_results", "SEARXNG_MAX_RESULTS", 16))
        )
        self.min_score = float(self._cfg("searxng_min_score", "SEARXNG_MIN_SCORE", 0.45))
        self.cache_ttl = max(
            0,
            int(self._cfg("searxng_cache_ttl_seconds", "SEARXNG_CACHE_TTL_SECONDS", 900)),
        )

    @staticmethod
    def _as_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def get_stock_data(self, symbol: str, start_date: str, end_date: str) -> str:
        raise NotImplementedError("cn_searxng only supports news data")

    def get_indicators(
        self, symbol: str, indicator: str, curr_date: str, look_back_days: int
    ) -> str:
        raise NotImplementedError("cn_searxng only supports news data")

    def get_fundamentals(self, ticker: str, curr_date: str = None) -> str:
        raise NotImplementedError("cn_searxng only supports news data")

    def get_balance_sheet(
        self, ticker: str, freq: str = "quarterly", curr_date: str = None
    ) -> str:
        raise NotImplementedError("cn_searxng only supports news data")

    def get_cashflow(
        self, ticker: str, freq: str = "quarterly", curr_date: str = None
    ) -> str:
        raise NotImplementedError("cn_searxng only supports news data")

    def get_income_statement(
        self, ticker: str, freq: str = "quarterly", curr_date: str = None
    ) -> str:
        raise NotImplementedError("cn_searxng only supports news data")

    def get_insider_transactions(self, symbol: str) -> str:
        raise NotImplementedError("cn_searxng does not provide insider transactions")

    def get_news(self, ticker: str, start_date: str, end_date: str) -> str:
        self._refresh_settings()
        info = self._normalize_cn_ticker(ticker)
        stock_name = self.config.get("stock_name") or self._resolve_stock_name(info["code6"])
        queries = self._build_stock_queries(stock_name, info)
        time_range = self._time_range_from_dates(start_date, end_date)
        items = self._run_queries(
            queries,
            time_range=time_range,
            limit=self.max_results,
            context_key=f"{info['code6']}|{start_date}|{end_date}",
        )
        if not items:
            raise NotImplementedError(
                "[cn_searxng] no qualified news results. Falling back to next news provider."
            )
        return self._format_news_markdown(
            items,
            title=f"{stock_name}({info['code6']}) SearXNG 新闻",
            period=f"{start_date} 至 {end_date}",
        )

    def _resolve_stock_name(self, code6: str) -> str:
        configured = self.config.get("stock_name_map")
        if isinstance(configured, dict):
            name = configured.get(code6)
            if name:
                return str(name).strip()
        return COMMON_CN_STOCK_NAMES.get(code6, code6)

    def get_global_news(
        self, curr_date: str, look_back_days: int = 7, limit: int = 50
    ) -> str:
        self._refresh_settings()
        queries = self._build_global_queries()
        time_range = "day" if look_back_days <= 1 else "week" if look_back_days <= 7 else "month"
        max_limit = min(max(1, limit), self.max_results)
        items = self._run_queries(
            queries,
            time_range=time_range,
            limit=max_limit,
            context_key=f"global|{curr_date}|{look_back_days}",
        )
        if not items:
            raise NotImplementedError(
                "[cn_searxng] no qualified global news results. Falling back to next news provider."
            )
        start = self._date_minus_days(curr_date, look_back_days)
        return self._format_news_markdown(
            items,
            title="A股全局 SearXNG 新闻",
            period=f"{start} 至 {curr_date}",
        )

    def _run_queries(
        self, queries: list[str], time_range: str, limit: int, context_key: str
    ) -> list[NewsItem]:
        all_items: list[NewsItem] = []
        search_failures = []
        for query in queries:
            cache_key = self._cache_key(query, time_range, context_key)
            cached = self._get_cache(cache_key)
            if cached is not None:
                all_items.extend(cached)
                continue
            try:
                items = self._search(query, time_range=time_range)
            except Exception as exc:
                search_failures.append(f"{type(exc).__name__}: {exc}")
                logger.warning("[cn_searxng] SearXNG search failed: %s", exc)
                continue
            self._set_cache(cache_key, items)
            all_items.extend(items)

        if not all_items:
            detail = "; ".join(search_failures[-3:]) or "empty result"
            raise NotImplementedError(
                f"[cn_searxng] SearXNG search failed: {detail}. "
                "Falling back to next news provider."
            )

        deduped = self._dedupe_items(all_items)
        if self.mode != "broad":
            deduped = [item for item in deduped if item.credibility_tier != 3]

        self._score_and_verify(deduped)
        filtered = [
            item
            for item in deduped
            if item.credibility_tier == 0 or item.confidence_score >= self.min_score
        ]
        filtered.sort(key=self._sort_key, reverse=True)

        if self.fetch_body:
            fetch_count = min(len(filtered), limit, 8)
            self._fetch_body_for_top_items(filtered[:fetch_count])
            self._score_and_verify(filtered)
            filtered.sort(key=self._sort_key, reverse=True)

        return filtered[:limit]

    def _search(self, query: str, time_range: str) -> list[NewsItem]:
        params = {
            "q": query,
            "format": "json",
            "categories": "news,general",
            "language": "zh-CN",
            "time_range": time_range,
            "safesearch": "0",
            "pageno": "1",
        }
        response = self.session.get(
            f"{self.base_url}/search",
            params=params,
            timeout=self.timeout,
            headers={"Accept": "application/json", "User-Agent": "TradingAgents-AShare/0.2"},
        )
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").lower()
        if "html" in content_type:
            raise ValueError("SearXNG returned HTML instead of JSON; check format=json support")
        try:
            data = response.json()
        except ValueError as exc:
            raise ValueError("SearXNG response is not valid JSON") from exc

        results = data.get("results") if isinstance(data, dict) else None
        if not isinstance(results, list):
            return []

        items: list[NewsItem] = []
        for row in results:
            if not isinstance(row, dict):
                continue
            title = str(row.get("title") or "").strip()
            url = self._clean_url(str(row.get("url") or "").strip())
            if not title or not url:
                continue
            domain = self._domain(url)
            tier = self._domain_tier(domain)
            if self.mode != "broad" and tier == 3:
                continue
            items.append(
                NewsItem(
                    title=title,
                    url=url,
                    source=domain,
                    snippet=str(row.get("content") or row.get("snippet") or "").strip(),
                    published_at=self._normalize_date(
                        row.get("publishedDate") or row.get("published_date") or row.get("date")
                    ),
                    engine=str(row.get("engine") or "").strip(),
                    credibility_tier=tier,
                )
            )
        return items

    def _build_stock_queries(self, stock_name: str, info: dict[str, str]) -> list[str]:
        code6 = info["code6"]
        ts_code = info["ts_code"]
        primary = stock_name if stock_name else code6

        strict_queries = [
            f"{primary} {code6} site:cninfo.com.cn",
            f"{primary} {code6} site:sse.com.cn",
            f"{primary} {code6} site:szse.cn",
            f"{primary} {code6} 公告 问询函 年报 半年报 季报 分红 停牌 复牌",
        ]
        balanced_queries = [
            f"{primary} {code6} site:cninfo.com.cn OR site:sse.com.cn OR site:szse.cn",
            f"{primary} {code6} 公告 问询函 年报 半年报 季报 分红 停牌 复牌",
            f"{primary} {code6} 业绩 净利润 营收 订单 合同 并购 重组",
            f"{primary} 股价 涨停 跌停 龙虎榜 资金流 机构调研",
            f"{primary} 监管 处罚 立案 诉讼 退市 减持 债务",
        ]
        broad_extra = [
            f"{primary} {ts_code} 研报 机构 评级",
            f"{primary} 市场情绪 传闻 讨论",
        ]
        if self.mode == "strict":
            return strict_queries
        if self.mode == "broad":
            return balanced_queries + broad_extra
        return balanced_queries

    def _build_global_queries(self) -> list[str]:
        strict_queries = [
            "A股 今日 市场 证监会 央行 政策 site:csrc.gov.cn OR site:pbc.gov.cn",
            "上证指数 深证成指 创业板 今日 site:sse.com.cn OR site:szse.cn",
            "中国 股市 宏观 经济 PMI 利率 汇率 site:stats.gov.cn OR site:pbc.gov.cn",
        ]
        balanced_queries = [
            "A股 今日 市场 证监会 央行 政策",
            "上证指数 深证成指 创业板 今日",
            "中国 股市 宏观 经济 PMI 利率 汇率",
            "半导体 新能源 医药 消费 房地产 银行 券商 今日",
        ]
        if self.mode == "strict":
            return strict_queries
        if self.mode == "broad":
            return balanced_queries + ["A股 舆情 热点 讨论 今日"]
        return balanced_queries

    def _score_and_verify(self, items: list[NewsItem]) -> None:
        clusters = self._cluster_by_title(items)
        for item in items:
            item.confidence_score = round(
                0.40 * self._source_score(item.credibility_tier)
                + 0.25 * self._freshness_score(item.published_at)
                + 0.20 * self._corroboration_score(item, clusters)
                + 0.15 * self._completeness_score(item),
                3,
            )
            item.verification_status = self._verification_status(item, clusters)

    def _fetch_body_for_top_items(self, items: list[NewsItem]) -> None:
        if BeautifulSoup is None:
            return
        for item in items:
            if item.credibility_tier not in (0, 1, 2):
                continue
            try:
                response = self.session.get(
                    item.url,
                    timeout=min(self.timeout, 5),
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
                        )
                    },
                )
                if not response.ok or not response.text:
                    continue
                soup = BeautifulSoup(response.text, "html.parser")
                for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                    tag.decompose()
                article = (
                    soup.find("article")
                    or soup.find(class_=re.compile("article|content|main|detail|正文", re.I))
                    or soup.body
                )
                text = article.get_text(" ", strip=True) if article else ""
                text = re.sub(r"\s+", " ", text).strip()
                if len(text) >= 80:
                    item.body_excerpt = text[:5000]
            except Exception as exc:
                logger.debug("[cn_searxng] body fetch failed for %s: %s", item.url, exc)

    def _format_news_markdown(self, items: list[NewsItem], title: str, period: str) -> str:
        lines = [
            f"## {title}",
            f"- provider: cn_searxng",
            f"- mode: {self.mode}",
            f"- period: {period}",
            "",
        ]
        for idx, item in enumerate(items, 1):
            lines.extend(
                [
                    f"### {idx}. {item.title}",
                    f"- 来源: {item.source}",
                    f"- URL: {item.url}",
                    f"- 时间: {item.published_at or '未知'}",
                    f"- 可信等级: Tier {item.credibility_tier if item.credibility_tier != 9 else 'Unknown'}",
                    f"- 可信分: {item.confidence_score:.3f}",
                    f"- 验证状态: {item.verification_status}",
                    f"- 搜索引擎: {item.engine or '未知'}",
                    f"- 摘要: {item.snippet or '无'}",
                ]
            )
            if item.body_excerpt:
                lines.append(f"- 正文摘录: {item.body_excerpt[:1200]}")
            lines.append("")
        return "\n".join(lines).strip()

    @staticmethod
    def _normalize_cn_ticker(ticker: str) -> dict[str, str]:
        raw = str(ticker or "").strip().upper()
        match = re.search(r"(\d{6})", raw)
        code6 = match.group(1) if match else raw
        if code6.startswith("6"):
            exchange = "SH"
        elif code6.startswith(("0", "3")):
            exchange = "SZ"
        elif code6.startswith(("4", "8", "9")):
            exchange = "BJ"
        else:
            exchange = ""
        return {
            "raw": raw,
            "code6": code6,
            "exchange": exchange,
            "ts_code": f"{code6}.{exchange}" if exchange else code6,
            "market_prefix": exchange.lower(),
        }

    @staticmethod
    def _time_range_from_dates(start_date: str, end_date: str) -> str:
        try:
            start = datetime.fromisoformat(str(start_date)[:10])
            end = datetime.fromisoformat(str(end_date)[:10])
            days = max((end - start).days, 0)
        except Exception:
            days = 7
        if days <= 1:
            return "day"
        if days <= 7:
            return "week"
        return "month"

    @staticmethod
    def _date_minus_days(curr_date: str, days: int) -> str:
        try:
            dt = datetime.fromisoformat(str(curr_date)[:10])
            return (dt - timedelta(days=days)).strftime("%Y-%m-%d")
        except Exception:
            return f"{days} days before {curr_date}"

    @staticmethod
    def _domain(url: str) -> str:
        return urlparse(url).netloc.lower().removeprefix("www.")

    @staticmethod
    def _clean_url(url: str) -> str:
        parsed = urlparse(url)
        query = [
            (key, val)
            for key, val in parse_qsl(parsed.query, keep_blank_values=True)
            if not key.lower().startswith(("utm_", "spm", "from", "ref"))
        ]
        return urlunparse(parsed._replace(query=urlencode(query)))

    @staticmethod
    def _domain_tier(domain: str) -> int:
        if any(domain == d or domain.endswith("." + d) for d in TIER0_DOMAINS):
            return 0
        if any(domain == d or domain.endswith("." + d) for d in TIER1_DOMAINS):
            return 1
        if any(domain == d or domain.endswith("." + d) for d in TIER3_DOMAINS):
            return 3
        if any(domain == d or domain.endswith("." + d) for d in TIER2_DOMAINS):
            return 2
        return 9

    @staticmethod
    def _source_score(tier: int) -> float:
        return {0: 1.0, 1: 0.85, 2: 0.68, 3: 0.35}.get(tier, 0.45)

    @staticmethod
    def _freshness_score(published_at: str | None) -> float:
        if not published_at:
            return 0.50
        dt = CnSearxngProvider._parse_datetime(published_at)
        if dt is None:
            return 0.50
        now = datetime.now(dt.tzinfo) if dt.tzinfo is not None else datetime.now()
        age_days = max((now - dt).days, 0)
        if age_days <= 1:
            return 1.00
        if age_days <= 3:
            return 0.80
        if age_days <= 7:
            return 0.65
        if age_days <= 30:
            return 0.45
        return 0.25

    @staticmethod
    def _completeness_score(item: NewsItem) -> float:
        if item.body_excerpt and item.title and item.url and item.source and item.published_at:
            return 1.00
        if item.body_excerpt:
            return 0.80
        if item.title and item.snippet and item.url:
            return 0.55
        if item.title and item.url:
            return 0.35
        return 0.20

    @staticmethod
    def _cluster_by_title(items: list[NewsItem]) -> dict[str, list[NewsItem]]:
        clusters: dict[str, list[NewsItem]] = {}
        for item in items:
            key = CnSearxngProvider._title_key(item.title)
            clusters.setdefault(key, []).append(item)
        return clusters

    @staticmethod
    def _title_key(title: str) -> str:
        normalized = re.sub(r"[^\w\u4e00-\u9fff]+", "", title.lower())
        return normalized[:42]

    @staticmethod
    def _corroboration_score(item: NewsItem, clusters: dict[str, list[NewsItem]]) -> float:
        if item.credibility_tier == 0:
            return 1.00
        peers = clusters.get(CnSearxngProvider._title_key(item.title), [])
        trusted_domains = {peer.source for peer in peers if peer.credibility_tier in (1, 2)}
        if len(trusted_domains) >= 2:
            return 0.85
        if item.credibility_tier in (1, 2):
            return 0.55
        if item.credibility_tier == 3:
            return 0.20
        return 0.35

    @staticmethod
    def _verification_status(item: NewsItem, clusters: dict[str, list[NewsItem]]) -> str:
        if item.credibility_tier == 0:
            return "official_verified"
        peers = clusters.get(CnSearxngProvider._title_key(item.title), [])
        trusted_domains = {peer.source for peer in peers if peer.credibility_tier in (1, 2)}
        if len(trusted_domains) >= 2:
            return "multi_source_verified"
        if item.credibility_tier == 1:
            return "trusted_media"
        if item.credibility_tier == 2:
            return "mainstream_portal"
        if item.credibility_tier == 3:
            return "social_or_unverified"
        return "unverified"

    @staticmethod
    def _normalize_date(value: Any) -> str | None:
        if not value:
            return None
        text = str(value).strip()
        dt = CnSearxngProvider._parse_datetime(text)
        if dt is not None:
            return dt.strftime("%Y-%m-%d")
        match = re.search(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})", text)
        if match:
            year, month, day = match.groups()
            return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
        return text[:32]

    @staticmethod
    def _parse_datetime(text: str) -> datetime | None:
        value = str(text).strip()
        for parser in (
            lambda s: datetime.fromisoformat(s.replace("Z", "+00:00")),
            parsedate_to_datetime,
        ):
            try:
                return parser(value)
            except Exception:
                continue
        return None

    @staticmethod
    def _dedupe_items(items: list[NewsItem]) -> list[NewsItem]:
        seen: set[str] = set()
        deduped: list[NewsItem] = []
        for item in items:
            parsed = urlparse(item.url)
            normalized_url = urlunparse(parsed._replace(fragment=""))
            key = hashlib.sha1(f"{item.title}|{normalized_url}".encode("utf-8")).hexdigest()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    def _cache_key(self, query: str, time_range: str, context_key: str) -> str:
        raw = f"{self.mode}|{query}|{time_range}|{context_key}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def _get_cache(self, key: str) -> list[NewsItem] | None:
        if self.cache_ttl <= 0:
            return None
        cached = self._cache.get(key)
        if cached is None:
            return None
        ts, value = cached
        if time.time() - ts > self.cache_ttl:
            self._cache.pop(key, None)
            return None
        return [NewsItem(**item.__dict__) for item in value]

    def _set_cache(self, key: str, value: list[NewsItem]) -> None:
        if self.cache_ttl <= 0:
            return
        self._cache[key] = (time.time(), [NewsItem(**item.__dict__) for item in value])

    @staticmethod
    def _sort_key(item: NewsItem) -> tuple[float, str]:
        return (item.confidence_score, item.published_at or "")
