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
    
    # Data vendor configuration
    "data_vendors": {
        "core_stock_apis": "cn_akshare,cn_baostock,yfinance",
        "technical_indicators": "cn_akshare,cn_baostock,yfinance",
        "fundamental_data": "cn_akshare,cn_baostock,yfinance",
        "news_data": "cn_searxng,cn_akshare,yfinance",
        "realtime_data": "cn_akshare",
    },
    "tool_vendors": {},
}
