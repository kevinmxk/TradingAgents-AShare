import os

DEFAULT_CONFIG = {
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("TA_RESULTS_DIR", "./results"),
    "data_cache_dir": os.path.join(
        os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
        "dataflows/data_cache",
    ),
    # LLM settings
    "llm_provider": os.getenv("TA_LLM_PROVIDER", "openai"),
    "deep_think_llm": os.getenv("TA_LLM_DEEP", "gpt-4o"),
    "quick_think_llm": os.getenv("TA_LLM_QUICK", "gpt-4o-mini"),
    "backend_url": os.getenv("TA_BASE_URL", "https://api.openai.com/v1"),
    "api_key": os.getenv("TA_API_KEY", ""),
    
    # Provider-specific thinking configuration
    "google_thinking_level": None,      # "high", "minimal", etc.
    "openai_reasoning_effort": None,    # "medium", "high", "low"
    
    # Debate and discussion settings
    "max_debate_rounds": int(os.getenv("TA_MAX_DEBATE") or "2"),
    "max_risk_discuss_rounds": int(os.getenv("TA_MAX_RISK") or "1"),
    "max_recur_limit": 100,
    
    # Prompt language control: zh, en, or auto
    "prompt_language": os.getenv("TA_LANGUAGE", "zh"),
    "prompt_language_by_provider": {},
    
    # Provider routing trace logs
    "provider_trace": os.getenv("TA_TRACE", "1").lower() in ("1", "true", "yes", "on"),

    # SearXNG news source configuration
    "searxng_base_url": os.getenv("SEARXNG_BASE_URL", "http://127.0.0.1:8888"),
    "searxng_mode": os.getenv("SEARXNG_MODE", "balanced"),
    "searxng_timeout": int(os.getenv("SEARXNG_TIMEOUT", "8")),
    "searxng_fetch_body": os.getenv("SEARXNG_FETCH_BODY", "true").lower() in ("1", "true", "yes", "on"),
    "searxng_max_results": int(os.getenv("SEARXNG_MAX_RESULTS", "16")),
    "searxng_min_score": float(os.getenv("SEARXNG_MIN_SCORE", "0.45")),
    "searxng_cache_ttl_seconds": int(os.getenv("SEARXNG_CACHE_TTL_SECONDS", "900")),

    # News provider strategy: fallback keeps current behavior; hybrid supplements
    # weak primary results; aggregate queries all configured news providers.
    "news_data_strategy": os.getenv("NEWS_DATA_STRATEGY", "hybrid"),
    "news_hybrid_min_items": int(os.getenv("NEWS_HYBRID_MIN_ITEMS", "8")),
    "news_hybrid_min_confidence": float(os.getenv("NEWS_HYBRID_MIN_CONFIDENCE", "0.70")),
    "news_aggregate_max_items": int(os.getenv("NEWS_AGGREGATE_MAX_ITEMS", "20")),
    "news_aggregate_max_chars": int(os.getenv("NEWS_AGGREGATE_MAX_CHARS", "20000")),
    "news_dedupe_enabled": os.getenv("NEWS_DEDUPE_ENABLED", "true").lower() in ("1", "true", "yes", "on"),

    # Tushare Pro structured A-share data source configuration.
    # User-saved frontend settings override these environment values at runtime.
    "tushare_enabled": os.getenv("TUSHARE_ENABLED", "false").lower() in ("1", "true", "yes", "on"),
    "tushare_token": os.getenv("TUSHARE_TOKEN", ""),
    "tushare_proxy_url": os.getenv("TUSHARE_PROXY_URL", ""),
    "tushare_timeout": int(os.getenv("TUSHARE_TIMEOUT", "10")),
    "tushare_rate_limit_per_minute": int(os.getenv("TUSHARE_RATE_LIMIT_PER_MINUTE", "40")),
    "tushare_cache_ttl_seconds": int(os.getenv("TUSHARE_CACHE_TTL_SECONDS", "86400")),
    "tushare_capability_cache_ttl_seconds": int(os.getenv("TUSHARE_CAPABILITY_CACHE_TTL_SECONDS", "86400")),
    "tushare_capabilities": {},
    "tushare_last_checked_at": None,
    
    # Data vendor configuration
    "data_vendors": {
        "core_stock_apis": "cn_tushare,cn_akshare,cn_baostock,yfinance",
        "technical_indicators": "cn_tushare,cn_akshare,cn_baostock,yfinance",
        "fundamental_data": "cn_tushare,cn_akshare,cn_baostock,yfinance",
        "news_data": "cn_searxng,cn_tushare,cn_akshare,yfinance",
        "cn_market_data": "cn_tushare,cn_akshare",
        "realtime_data": "cn_akshare",
    },
    "tool_vendors": {},
}
