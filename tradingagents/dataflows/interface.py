import os
import re

from .alpha_vantage_common import AlphaVantageRateLimitError
from .config import get_config
from .providers import build_default_registry

# Tools organized by category
TOOLS_CATEGORIES = {
    "core_stock_apis": {
        "description": "OHLCV stock price data",
        "tools": ["get_stock_data"],
    },
    "technical_indicators": {
        "description": "Technical analysis indicators",
        "tools": ["get_indicators"],
    },
    "fundamental_data": {
        "description": "Company fundamentals",
        "tools": [
            "get_fundamentals",
            "get_balance_sheet",
            "get_cashflow",
            "get_income_statement",
        ],
    },
    "news_data": {
        "description": "News and insider data",
        "tools": [
            "get_news",
            "get_global_news",
            "get_insider_transactions",
        ],
    },
    "realtime_data": {
        "description": "Real-time market quotes",
        "tools": ["get_realtime_quotes"],
    },
    "cn_market_data": {
        "description": "China A-share market sentiment and fund flow data",
        "tools": [
            "get_board_fund_flow",
            "get_individual_fund_flow",
            "get_lhb_detail",
            "get_zt_pool",
            "get_hot_stocks_xq",
        ],
    },
}

_registry = build_default_registry()

VENDOR_LIST = _registry.list_names()


def _is_trace_enabled() -> bool:
    env_value = os.getenv("TA_TRACE")
    if env_value is not None:
        return env_value.strip().lower() in ("1", "true", "yes", "on")

    config = get_config()
    return bool(config.get("provider_trace", True))


def _trace(msg: str) -> None:
    if _is_trace_enabled():
        print(f"[provider-trace] {msg}", flush=True)


_TRACE_KEYS = ("symbol", "ticker", "start_date", "end_date", "curr_date", "indicator")


def _summarize_args(args: tuple, kwargs: dict) -> str:
    """格式化首参数（通常是 symbol）和常见日期/指标键，用于 trace 日志定位。"""
    parts = []
    if args:
        # 约定：所有 provider 方法首参数为 symbol/ticker
        parts.append(f"symbol={args[0]!r}")
        if len(args) >= 2:
            parts.append(f"arg2={args[1]!r}")
        if len(args) >= 3:
            parts.append(f"arg3={args[2]!r}")
    for k, v in kwargs.items():
        if k in _TRACE_KEYS:
            parts.append(f"{k}={v!r}")
    return " ".join(parts)


def get_category_for_method(method: str) -> str:
    """Get the category that contains the specified method."""
    for category, info in TOOLS_CATEGORIES.items():
        if method in info["tools"]:
            return category
    raise ValueError(f"Method '{method}' not found in any category")


def get_vendor(category: str, method: str = None) -> str:
    """Get configured vendor for category or tool method."""
    config = get_config()

    if method:
        tool_vendors = config.get("tool_vendors", {})
        if method in tool_vendors:
            return tool_vendors[method]

    return config.get("data_vendors", {}).get(category, "yfinance")


def _resolve_vendor_chain(method: str, configured_vendor: str) -> list[str]:
    configured = [v.strip() for v in configured_vendor.split(",") if v.strip()]
    fallback = configured.copy()

    for provider_name in _registry.list_names():
        if provider_name in fallback:
            continue
        provider = _registry.get(provider_name)
        # 占位 provider（如 cn_stub）不自动追加进 fallback chain，
        # 避免污染日志和兜底链；用户显式配置仍可强制使用。
        if getattr(provider, "is_placeholder", False):
            continue
        fallback.append(provider_name)

    return fallback


def route_to_vendor(method: str, *args, **kwargs):
    """Route method calls to provider implementations with fallback support."""
    category = get_category_for_method(method)
    vendor_config = get_vendor(category, method)
    fallback_vendors = _resolve_vendor_chain(method, vendor_config)
    args_summary = _summarize_args(args, kwargs)
    last_exc = None
    provider_errors = []
    _trace(
        f"method={method} {args_summary} category={category} "
        f"configured='{vendor_config}' chain={fallback_vendors}"
    )

    for vendor in fallback_vendors:
        provider = _registry.get(vendor)
        if provider is None:
            _trace(f"method={method} {args_summary} vendor={vendor} status=skip reason=not-registered")
            provider_errors.append(f"{vendor}: not-registered")
            continue

        impl_func = getattr(provider, method, None)
        if impl_func is None:
            _trace(f"method={method} {args_summary} vendor={vendor} status=skip reason=not-implemented")
            provider_errors.append(f"{vendor}: not-implemented")
            continue

        try:
            result = impl_func(*args, **kwargs)
            _trace(f"method={method} {args_summary} vendor={vendor} status=hit")
            return result
        except (AlphaVantageRateLimitError, NotImplementedError) as exc:
            last_exc = exc
            # Try next provider for transient/routing issues or placeholder providers.
            _trace(
                f"method={method} {args_summary} vendor={vendor} status=fallback "
                f"reason={type(exc).__name__}: {exc}"
            )
            provider_errors.append(f"{vendor}: {type(exc).__name__}: {exc}")
            continue
        except Exception as exc:
            # Provider-specific runtime/parsing errors (e.g., schema changes, KeyError)
            # should not terminate the full chain; fall through to next vendor.
            last_exc = exc
            _trace(
                f"method={method} {args_summary} vendor={vendor} status=fallback "
                f"reason={type(exc).__name__}: {exc}"
            )
            provider_errors.append(f"{vendor}: {type(exc).__name__}: {exc}")
            continue

    _trace(f"method={method} {args_summary} status=failed reason=no-available-vendor")
    detail = f" Provider errors: {' | '.join(provider_errors)}" if provider_errors else ""
    if last_exc is not None:
        raise RuntimeError(
            f"No available vendor for method '{method}'. "
            f"Configured chain: {fallback_vendors}. "
            f"Last error: {type(last_exc).__name__}: {last_exc}."
            f"{detail}"
        ) from last_exc
    raise RuntimeError(
        f"No available vendor for method '{method}'. "
        f"Configured chain: {fallback_vendors}."
        f"{detail}"
    )


_NEWS_METHODS = {"get_news", "get_global_news"}


def _news_strategy_config() -> dict:
    config = get_config()
    strategy = str(config.get("news_data_strategy", "hybrid") or "hybrid").strip().lower()
    if strategy not in {"fallback", "hybrid", "aggregate"}:
        strategy = "hybrid"
    return {
        "strategy": strategy,
        "min_items": max(1, int(config.get("news_hybrid_min_items", 8) or 8)),
        "min_confidence": float(config.get("news_hybrid_min_confidence", 0.70) or 0.70),
        "max_items": max(1, int(config.get("news_aggregate_max_items", 20) or 20)),
        "max_chars": max(1000, int(config.get("news_aggregate_max_chars", 20000) or 20000)),
        "dedupe": bool(config.get("news_dedupe_enabled", True)),
    }


def _news_metrics(markdown: str) -> tuple[int, float]:
    text = str(markdown or "")
    item_markers = [
        len(re.findall(r"(?m)^###\s+\d+[\.\u3001]", text)),
        len(re.findall(r"(?m)^###\s+", text)),
        len(re.findall(r"(?im)^\s*[-*]?\s*(?:URL|Link|链接)[:：]\s*https?://", text)),
        len(re.findall(r"https?://", text)),
    ]
    item_count = max(item_markers) if item_markers else 0

    scores = []
    for pattern in (
        r"(?:可信分|confidence(?:_score)?|score)\s*[:：]?\s*([01](?:\.\d+)?)",
        r"可信[^\d]{0,12}([01](?:\.\d+)?)",
        r"confidence[^\d]{0,20}([01](?:\.\d+)?)",
    ):
        for match in re.findall(pattern, text, flags=re.IGNORECASE):
            try:
                scores.append(float(match))
            except (TypeError, ValueError):
                pass
    return item_count, max(scores) if scores else 0.0


def _trim_news_markdown(markdown: str, max_items: int) -> str:
    text = str(markdown or "").strip()
    if max_items <= 0:
        return text
    parts = re.split(r"(?m)(?=^###\s+)", text)
    if len(parts) <= 1:
        return text
    header = parts[0].rstrip()
    items = [p.rstrip() for p in parts[1:] if p.strip()]
    trimmed = "\n\n".join(items[:max_items])
    return (header + "\n\n" + trimmed).strip() if header else trimmed.strip()


def _dedupe_news_blocks(blocks: list[tuple[str, str]], max_items: int) -> list[tuple[str, str]]:
    """Light provider-block dedupe based on first URL/title; not strict item dedupe."""
    seen: set[str] = set()
    output: list[tuple[str, str]] = []
    for vendor, markdown in blocks:
        text = str(markdown or "").strip()
        urls = re.findall(r"https?://[^\s)\]>\"']+", text)
        title_match = re.search(r"(?m)^###\s+(?:\d+[\.\u3001]\s*)?(.+)$", text)
        key_source = urls[0] if urls else title_match.group(1) if title_match else text[:160]
        key = re.sub(r"\W+", "", key_source.lower())
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        output.append((vendor, _trim_news_markdown(text, max_items)))
    return output


def _format_news_aggregate(method: str, blocks: list[tuple[str, str]], skipped: list[str], cfg: dict) -> str:
    title = "聚合新闻结果" if method == "get_news" else "聚合全局新闻结果"
    lines = [
        f"## {title}",
        f"- strategy: {cfg['strategy']}",
        f"- providers_hit: {', '.join(vendor for vendor, _ in blocks) or 'none'}",
    ]
    if skipped:
        _trace(f"method={method} strategy={cfg['strategy']} providers_skipped={'; '.join(skipped)}")
    lines.append("")
    for vendor, markdown in blocks:
        lines.extend([f"### 来源：{vendor}", str(markdown).strip(), ""])
    return "\n".join(lines).strip()


def _cap_news_markdown_length(markdown: str, max_chars: int) -> str:
    text = str(markdown or "").strip()
    if len(text) <= max_chars:
        return text
    suffix = "\n\n[content truncated by NEWS_AGGREGATE_MAX_CHARS]"
    return text[: max(0, max_chars - len(suffix))].rstrip() + suffix


def route_news_with_strategy(method: str, *args, **kwargs):
    """Route news calls using fallback, hybrid, or aggregate strategy.

    Provider outputs remain Markdown strings so existing analysts can consume
    the result without provider-level schema changes.
    """
    if method not in _NEWS_METHODS:
        return route_to_vendor(method, *args, **kwargs)

    cfg = _news_strategy_config()
    if cfg["strategy"] == "fallback":
        return route_to_vendor(method, *args, **kwargs)

    vendor_config = get_vendor("news_data", method)
    fallback_vendors = [v.strip() for v in vendor_config.split(",") if v.strip()]
    args_summary = _summarize_args(args, kwargs)
    _trace(
        f"method={method} {args_summary} category=news_data "
        f"strategy={cfg['strategy']} configured='{vendor_config}' chain={fallback_vendors}"
    )

    blocks: list[tuple[str, str]] = []
    skipped: list[str] = []
    last_exc = None
    for idx, vendor in enumerate(fallback_vendors):
        provider = _registry.get(vendor)
        if provider is None:
            skipped.append(f"{vendor}: not-registered")
            _trace(f"method={method} {args_summary} vendor={vendor} status=skip reason=not-registered")
            continue
        impl_func = getattr(provider, method, None)
        if impl_func is None:
            skipped.append(f"{vendor}: not-implemented")
            _trace(f"method={method} {args_summary} vendor={vendor} status=skip reason=not-implemented")
            continue
        try:
            result = impl_func(*args, **kwargs)
            text = str(result or "").strip()
            if not text:
                raise NotImplementedError(f"{vendor} returned empty news")
            blocks.append((vendor, text))
            items, confidence = _news_metrics(text)
            _trace(
                f"method={method} {args_summary} vendor={vendor} status=hit "
                f"items={items} confidence={confidence:.3f}"
            )
            if cfg["strategy"] == "hybrid" and idx == 0:
                near_min_items = max(1, cfg["min_items"] - 2)
                high_confidence = min(1.0, cfg["min_confidence"] + 0.10)
                enough_primary = (
                    items >= cfg["min_items"] and confidence >= cfg["min_confidence"]
                ) or (
                    items >= near_min_items and confidence >= high_confidence
                )
                if enough_primary:
                    return result
            if cfg["strategy"] == "hybrid" and idx > 0:
                continue
        except (AlphaVantageRateLimitError, NotImplementedError) as exc:
            last_exc = exc
            skipped.append(f"{vendor}: {type(exc).__name__}")
            _trace(
                f"method={method} {args_summary} vendor={vendor} status=fallback "
                f"reason={type(exc).__name__}: {exc}"
            )
            continue
        except Exception as exc:
            last_exc = exc
            skipped.append(f"{vendor}: {type(exc).__name__}")
            _trace(
                f"method={method} {args_summary} vendor={vendor} status=fallback "
                f"reason={type(exc).__name__}: {exc}"
            )
            continue

    if blocks:
        max_per_provider = max(1, cfg["max_items"] // max(1, len(blocks)))
        merged = _dedupe_news_blocks(blocks, max_per_provider) if cfg["dedupe"] else [
            (vendor, _trim_news_markdown(text, max_per_provider)) for vendor, text in blocks
        ]
        return _cap_news_markdown_length(_format_news_aggregate(method, merged, skipped, cfg), cfg["max_chars"])

    if last_exc is not None:
        raise RuntimeError(
            f"No available news vendor for method '{method}'. "
            f"Configured chain: {fallback_vendors}. "
            f"Last error: {type(last_exc).__name__}: {last_exc}"
        ) from last_exc
    raise RuntimeError(
        f"No available news vendor for method '{method}'. "
        f"Configured chain: {fallback_vendors}"
    )
