# TradingAgents-AShare SearXNG 新闻源补丁开发说明

本文档用于指导 Codex 在本地 Windows 开发机上的 `KylinMountain/TradingAgents-AShare` 项目中开发一个 `cn_searxng` 新闻数据源补丁。

目标不是简单把 SearXNG 搜索结果塞进 LLM，而是实现一个可配置、可缓存、可评分、可追溯、能与现有新闻数据源链路自然 fallback 的新闻 provider。

默认部署假设：

- TradingAgents-AShare 已克隆到本地开发机。
- SearXNG 已部署并可访问。
- 线上服务器建议默认地址：`http://127.0.0.1:8888`
- 当前没有鉴权。
- 默认检索模式：`balanced`
- 允许抓取新闻正文。

---

## 一、先读代码，不要直接改

请 Codex 先在项目根目录执行代码阅读，确认本地版本的接口形态。必须重点阅读：

```text
tradingagents/dataflows/providers/base.py
tradingagents/dataflows/providers/registry.py
tradingagents/dataflows/providers/cn_akshare_provider.py
tradingagents/dataflows/providers/yfinance_provider.py
tradingagents/dataflows/interface.py
tradingagents/default_config.py
tradingagents/agents/analysts/news_analyst.py
```

如果项目存在后端和前端配置模块，也继续阅读：

```text
backend/
frontend/
web/
app/
server/
```

阅读目标：

1. 确认 `BaseMarketDataProvider` 的抽象方法签名。
2. 确认现有 provider 的命名方式，例如 `provider_name`、`name`、`capabilities`、注册函数等。
3. 确认 `get_news` 和 `get_global_news` 的返回类型。通常可能是字符串、字典或列表，新增 provider 必须保持一致。
4. 确认 `default_config.py` 里 `data_vendors.news_data` 的格式，是字符串、列表，还是嵌套字典。
5. 确认 `interface.py` 如何调用 provider 和 fallback。
6. 确认新闻分析员如何消费新闻文本，是否需要 Markdown 格式。

如果本地接口与本文档代码片段不完全一致，以本地项目接口为准。

---

## 二、补丁目标

新增新闻源：

```text
cn_searxng
```

推荐默认新闻源链路：

```python
news_data = "cn_searxng,cn_akshare,yfinance"
```

如果希望保守上线，可以先用：

```python
news_data = "cn_akshare,cn_searxng,yfinance"
```

最终目标能力：

1. 对个股新闻实现 `get_news(ticker, start_date, end_date)`。
2. 对宏观/全局新闻实现 `get_global_news(curr_date, look_back_days, limit)`。
3. 支持 SearXNG JSON Search API。
4. 支持来源白名单、黑名单、可信度分级。
5. 支持多查询模板，覆盖官方公告、权威媒体、市场影响、风险事件。
6. 支持结果去重。
7. 支持可选正文抓取。
8. 支持缓存，避免同一 ticker 在一次分析中反复请求。
9. 支持超时、异常降级，不阻塞整个分析链路。
10. 输出给 LLM 的新闻必须包含来源、URL、时间、可信度、验证状态。

---

## 三、SearXNG API 规则

SearXNG Search API 文档：

```text
https://docs.searxng.org/dev/search_api.html
```

基础请求：

```http
GET {SEARXNG_BASE_URL}/search
```

基础参数：

```text
q=搜索关键词
format=json
categories=news,general
language=zh-CN
time_range=day|week|month|year
pageno=1
safesearch=0
```

注意：

- SearXNG 需要在服务端配置中允许 JSON 输出；如果请求返回 403 或 HTML，需要检查 SearXNG 的 `formats` 设置是否包含 `json`。
- `categories=news` 的有效性取决于 SearXNG 实例启用了哪些 engines。若新闻分类返回过少，应 fallback 到 `categories=general`。
- 搜索结果的 `publishedDate` 不一定存在，也不一定可靠，必须允许为空。

---

## 四、检索模式设计

新增配置项：

```text
SEARXNG_MODE=balanced
```

支持三种模式：

```text
strict      严格权威：优先官方公告和权威媒体，结果少但可信。
balanced    平衡模式：官方 + 权威媒体 + 主流财经门户。
broad       广覆盖：包含更多门户和社区，适合舆情，但低可信结果要降权。
```

本补丁默认使用 `balanced`。

---

## 五、个股新闻检索规则

个股新闻不要只搜股票代码。必须组合：

```text
股票简称
6 位股票代码
交易所后缀代码，例如 600519.SH / 000001.SZ
关键事件词
```

### 5.1 代码归一化

需要实现工具函数：

```python
def normalize_cn_ticker(ticker: str) -> dict:
    """
    输入可能是：
    - 600519
    - 600519.SH
    - SH600519
    - sh.600519
    - 000001.SZ

    输出：
    {
        "raw": 原始输入,
        "code6": "600519",
        "ts_code": "600519.SH",
        "exchange": "SH",
        "market_prefix": "sh",
    }
    """
```

规则：

```text
6 开头通常是 SH
0/3 开头通常是 SZ
8/4/9 开头通常是 BJ
```

### 5.2 股票简称

如果现有项目已有股票名称查询函数，复用它。否则：

1. 优先从项目已有 A 股 provider 获取股票名称。
2. 获取失败时只用代码查询。
3. 不要因为名称查不到而让新闻 provider 报错。

### 5.3 个股查询模板

平衡模式下建议生成 4 组查询。

#### 官方公告查询

```text
("{股票简称}" OR "{code6}" OR "{ts_code}") (公告 OR 问询函 OR 监管函 OR 年报 OR 半年报 OR 季报 OR 分红 OR 停牌 OR 复牌)
```

若 SearXNG 对 `OR` 支持不稳定，可以拆成多个简单查询：

```text
{股票简称} 公告
{股票简称} 问询函
{股票简称} 年报
{code6} 公告
```

官方站点优先查询：

```text
{股票简称} {code6} site:cninfo.com.cn
{股票简称} {code6} site:sse.com.cn
{股票简称} {code6} site:szse.cn
{股票简称} {code6} site:bse.cn
```

#### 权威财经媒体查询

```text
{股票简称} {code6} 业绩 OR 净利润 OR 营收 OR 订单 OR 合同 OR 并购 OR 重组
```

如果 `OR` 效果不好，拆成：

```text
{股票简称} 业绩
{股票简称} 净利润
{股票简称} 合同
{股票简称} 重组
```

#### 市场影响事件查询

```text
{股票简称} 股价 OR 涨停 OR 跌停 OR 龙虎榜 OR 资金流 OR 机构调研
```

拆分备用：

```text
{股票简称} 涨停
{股票简称} 龙虎榜
{股票简称} 机构调研
```

#### 风险事件查询

```text
{股票简称} 监管 OR 处罚 OR 立案 OR 诉讼 OR 退市 OR 减持 OR 爆雷 OR 债务
```

拆分备用：

```text
{股票简称} 处罚
{股票简称} 立案
{股票简称} 减持
{股票简称} 诉讼
```

---

## 六、全局新闻检索规则

用于 `get_global_news(curr_date, look_back_days, limit)`。

平衡模式下建议查询：

```text
A股 今日 市场 证监会 央行 政策
上证指数 深证成指 创业板 今日
中国 股市 宏观 经济 PMI 利率 汇率
半导体 新能源 医药 消费 房地产 银行 券商 今日
```

如果是交易日盘前/盘中，优先：

```text
A股 盘前 要闻
A股 午评
A股 收评
证监会 最新
央行 最新
```

如果 `look_back_days <= 1`：

```text
time_range=day
```

如果 `look_back_days <= 7`：

```text
time_range=week
```

否则：

```text
time_range=month
```

---

## 七、可信来源分级

在 provider 中内置域名等级表，用户可通过配置覆盖或追加。

### Tier 0：官方/公告源

```text
cninfo.com.cn
sse.com.cn
szse.cn
bse.cn
csrc.gov.cn
pbc.gov.cn
stats.gov.cn
ndrc.gov.cn
mof.gov.cn
```

默认分数：

```text
1.00
```

验证状态：

```text
official_verified
```

### Tier 1：权威财经媒体

```text
stcn.com
cs.com.cn
cnstock.com
cls.cn
yicai.com
xinhuanet.com
people.com.cn
21jingji.com
caixin.com
```

默认分数：

```text
0.85
```

验证状态：

```text
trusted_media
```

### Tier 2：主流财经门户/行情平台

```text
eastmoney.com
finance.sina.com.cn
stock.finance.sina.com.cn
finance.qq.com
money.163.com
10jqka.com.cn
hexun.com
jrj.com.cn
```

默认分数：

```text
0.68
```

验证状态：

```text
mainstream_portal
```

### Tier 3：社区/自媒体/低可信来源

```text
guba.eastmoney.com
xueqiu.com
baijiahao.baidu.com
mp.weixin.qq.com
zhihu.com
bilibili.com
tieba.baidu.com
```

默认分数：

```text
0.35
```

验证状态：

```text
social_or_unverified
```

默认策略：

- `strict` 模式过滤 Tier 3。
- `balanced` 模式默认过滤 Tier 3，除非关键词是“市场情绪/传闻/讨论”。
- `broad` 模式保留 Tier 3，但必须标注低可信，不能作为事实依据。

---

## 八、新闻质量评分

每条新闻计算：

```text
final_score =
  0.40 * source_score
  + 0.25 * freshness_score
  + 0.20 * corroboration_score
  + 0.15 * completeness_score
```

### 8.1 source_score

按域名 Tier 计算：

```text
Tier 0: 1.00
Tier 1: 0.85
Tier 2: 0.68
Tier 3: 0.35
Unknown: 0.45
```

### 8.2 freshness_score

如果能解析发布时间：

```text
24 小时内：1.00
3 天内：0.80
7 天内：0.65
30 天内：0.45
超过 30 天：0.25
```

如果没有发布时间：

```text
0.50
```

### 8.3 corroboration_score

同一事件被多源验证：

```text
官方源单条：1.00
两个及以上不同 Tier 1/2 域名：0.85
单一 Tier 1/2 来源：0.55
未知来源单条：0.35
Tier 3 单条：0.20
```

### 8.4 completeness_score

```text
抓到正文 + 标题 + URL + 来源 + 发布时间：1.00
抓到正文，但缺发布时间：0.80
只有标题 + 摘要 + URL：0.55
只有标题 + URL：0.35
```

默认过滤阈值：

```text
SEARXNG_MIN_SCORE=0.45
```

对于 Tier 0 官方公告，即使分数低也保留。

---

## 九、正文抓取规则

正文抓取是为了让 LLM 不只依赖搜索摘要。

启用配置：

```text
SEARXNG_FETCH_BODY=true
```

抓取限制：

```text
只抓 Tier 0 / Tier 1 / Tier 2
默认不抓 Tier 3
单页面超时 5 秒
正文最大长度 4000-6000 字符
每次个股分析最多抓 5-8 篇正文
失败不报错，只降 completeness_score
```

优先使用项目已有依赖。如果没有正文抽取依赖：

1. 先用 `requests` 或 `httpx` 获取 HTML。
2. 用 `BeautifulSoup` 提取正文。
3. 去掉 `script`、`style`、`nav`、`footer`、广告。
4. 提取正文时优先 `<article>`，其次常见 class，例如 `content`、`article`、`main`、`detail`。
5. 如果项目已有 `readability-lxml` 或 `trafilatura`，可以优先使用。

不建议第一版引入太重的新依赖。如果新增依赖，必须修改 `pyproject.toml` 或 `requirements.txt`。

---

## 十、缓存规则

必须加缓存，否则一次多 agent 分析会反复打 SearXNG。

内存缓存即可先上线：

```text
key = hash(mode + ticker/query + start_date + end_date + time_range)
ttl = 900 秒
```

配置：

```text
SEARXNG_CACHE_TTL_SECONDS=900
```

如果项目已有统一缓存目录，可扩展为磁盘缓存：

```text
data/cache/searxng_news/
```

第一版建议内存缓存即可，简单稳定。

---

## 十一、异常与降级

provider 必须满足：

1. SearXNG 不通时，不抛出未捕获异常。
2. JSON 解析失败时，返回空新闻或错误提示字符串，让上层 fallback 到 AkShare。
3. 单个查询失败，不影响其他查询。
4. 正文抓取失败，不影响搜索结果。
5. SearXNG 返回 HTML 时，提示用户检查 `format=json` 配置。
6. 所有网络请求必须有 timeout。

建议错误输出：

```text
[cn_searxng] SearXNG search failed: {error}. Falling back to next news provider.
```

如果现有 provider 约定是抛异常触发 fallback，则抛自定义异常；如果约定是返回空字符串，则返回空字符串。必须跟 `interface.py` 保持一致。

---

## 十二、建议新增文件

### 12.1 新增 provider

```text
tradingagents/dataflows/providers/cn_searxng_provider.py
```

建议结构：

```python
from __future__ import annotations

import os
import re
import time
import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

import requests
from bs4 import BeautifulSoup

from .base import BaseMarketDataProvider

logger = logging.getLogger(__name__)


@dataclass
class NewsItem:
    title: str
    url: str
    source: str = ""
    snippet: str = ""
    published_at: str | None = None
    body_excerpt: str = ""
    credibility_tier: int = 9
    confidence_score: float = 0.0
    verification_status: str = "unverified"
    engine: str = ""


class CnSearxngProvider(BaseMarketDataProvider):
    provider_name = "cn_searxng"

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.base_url = self._cfg("searxng_base_url", "SEARXNG_BASE_URL", "http://127.0.0.1:8888").rstrip("/")
        self.mode = self._cfg("searxng_mode", "SEARXNG_MODE", "balanced")
        self.timeout = float(self._cfg("searxng_timeout", "SEARXNG_TIMEOUT", 8))
        self.fetch_body = str(self._cfg("searxng_fetch_body", "SEARXNG_FETCH_BODY", "true")).lower() in {"1", "true", "yes", "on"}
        self.max_results = int(self._cfg("searxng_max_results", "SEARXNG_MAX_RESULTS", 16))
        self.min_score = float(self._cfg("searxng_min_score", "SEARXNG_MIN_SCORE", 0.45))
        self.cache_ttl = int(self._cfg("searxng_cache_ttl_seconds", "SEARXNG_CACHE_TTL_SECONDS", 900))
        self.session = requests.Session()
        self._cache: dict[str, tuple[float, list[NewsItem]]] = {}

    def _cfg(self, key: str, env_key: str, default: Any) -> Any:
        if isinstance(self.config, dict) and key in self.config:
            return self.config[key]
        return os.getenv(env_key, default)

    # IMPORTANT:
    # Adjust these method signatures to match local BaseMarketDataProvider exactly.
    def get_news(self, ticker: str, start_date: str, end_date: str, **kwargs: Any) -> str:
        ticker_info = self._normalize_cn_ticker(ticker)
        stock_name = kwargs.get("stock_name") or ticker_info["code6"]
        queries = self._build_stock_queries(stock_name, ticker_info)
        time_range = self._time_range_from_dates(start_date, end_date)
        items = self._run_queries(queries, time_range=time_range, limit=self.max_results)
        return self._format_news_markdown(items, title=f"{stock_name}({ticker_info['code6']}) SearXNG 新闻")

    def get_global_news(self, curr_date: str, look_back_days: int = 7, limit: int = 10, **kwargs: Any) -> str:
        queries = self._build_global_queries()
        time_range = "day" if look_back_days <= 1 else "week" if look_back_days <= 7 else "month"
        items = self._run_queries(queries, time_range=time_range, limit=limit)
        return self._format_news_markdown(items, title="A股全局 SearXNG 新闻")

    def _run_queries(self, queries: list[str], time_range: str, limit: int) -> list[NewsItem]:
        all_items: list[NewsItem] = []
        for query in queries:
            cache_key = self._cache_key(query, time_range)
            cached = self._get_cache(cache_key)
            if cached is not None:
                all_items.extend(cached)
                continue
            try:
                items = self._search(query, time_range=time_range)
                self._set_cache(cache_key, items)
                all_items.extend(items)
            except Exception as exc:
                logger.warning("cn_searxng query failed: %s", exc)

        deduped = self._dedupe_items(all_items)
        self._score_and_verify(deduped)
        filtered = [
            item for item in deduped
            if item.confidence_score >= self.min_score or item.credibility_tier == 0
        ]
        filtered.sort(key=lambda x: (x.confidence_score, x.published_at or ""), reverse=True)

        if self.fetch_body:
            self._fetch_body_for_top_items(filtered[: min(limit, 8)])

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
        resp = self.session.get(f"{self.base_url}/search", params=params, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        items = []
        for row in results:
            title = (row.get("title") or "").strip()
            url = self._clean_url((row.get("url") or "").strip())
            if not title or not url:
                continue
            domain = self._domain(url)
            items.append(
                NewsItem(
                    title=title,
                    url=url,
                    source=domain,
                    snippet=(row.get("content") or row.get("snippet") or "").strip(),
                    published_at=self._normalize_date(row.get("publishedDate") or row.get("published_date")),
                    engine=(row.get("engine") or "").strip(),
                    credibility_tier=self._domain_tier(domain),
                )
            )
        return items

    def _build_stock_queries(self, stock_name: str, ticker_info: dict[str, str]) -> list[str]:
        code6 = ticker_info["code6"]
        ts_code = ticker_info["ts_code"]
        base_terms = [stock_name, code6, ts_code]
        primary = stock_name if stock_name and stock_name != code6 else code6

        if self.mode == "strict":
            return [
                f'{primary} {code6} site:cninfo.com.cn',
                f'{primary} {code6} site:sse.com.cn',
                f'{primary} {code6} site:szse.cn',
                f'{primary} {code6} 公告 问询函',
            ]

        if self.mode == "broad":
            return [
                f'{primary} {code6} 公告',
                f'{primary} {code6} 业绩 净利润 营收',
                f'{primary} 股价 涨停 跌停 龙虎榜 资金流',
                f'{primary} 监管 处罚 立案 诉讼 减持',
                f'{primary} 机构 调研 研报',
                f'{primary} 股吧 雪球 讨论',
            ]

        return [
            f'{primary} {code6} site:cninfo.com.cn OR site:sse.com.cn OR site:szse.cn',
            f'{primary} {code6} 公告 问询函 年报 半年报 季报 分红 停牌 复牌',
            f'{primary} {code6} 业绩 净利润 营收 订单 合同 并购 重组',
            f'{primary} 股价 涨停 跌停 龙虎榜 资金流 机构调研',
            f'{primary} 监管 处罚 立案 诉讼 退市 减持 债务',
        ]

    def _build_global_queries(self) -> list[str]:
        if self.mode == "strict":
            return [
                "证监会 A股 最新 site:csrc.gov.cn",
                "央行 利率 汇率 最新 site:pbc.gov.cn",
                "A股 政策 上交所 深交所 北交所",
            ]
        return [
            "A股 今日 市场 证监会 央行 政策",
            "上证指数 深证成指 创业板 今日",
            "中国 股市 宏观 经济 PMI 利率 汇率",
            "半导体 新能源 医药 消费 房地产 银行 券商 今日",
        ]

    def _score_and_verify(self, items: list[NewsItem]) -> None:
        clusters = self._cluster_by_title(items)
        for item in items:
            source_score = self._source_score(item.credibility_tier)
            freshness_score = self._freshness_score(item.published_at)
            corroboration_score = self._corroboration_score(item, clusters)
            completeness_score = self._completeness_score(item)
            item.confidence_score = round(
                0.40 * source_score
                + 0.25 * freshness_score
                + 0.20 * corroboration_score
                + 0.15 * completeness_score,
                3,
            )
            item.verification_status = self._verification_status(item, clusters)

    def _fetch_body_for_top_items(self, items: list[NewsItem]) -> None:
        for item in items:
            if item.credibility_tier > 2:
                continue
            try:
                resp = self.session.get(item.url, timeout=min(self.timeout, 5), headers={"User-Agent": "Mozilla/5.0"})
                if not resp.ok or not resp.text:
                    continue
                soup = BeautifulSoup(resp.text, "html.parser")
                for tag in soup(["script", "style", "nav", "footer", "header"]):
                    tag.decompose()
                article = soup.find("article") or soup.find(class_=re.compile("article|content|main|detail", re.I)) or soup.body
                text = re.sub(r"\s+", " ", article.get_text(" ", strip=True) if article else "")
                item.body_excerpt = text[:5000]
            except Exception:
                continue

    def _format_news_markdown(self, items: list[NewsItem], title: str) -> str:
        if not items:
            return f"## {title}\n\n未从 SearXNG 检索到满足可信度阈值的新闻。"
        lines = [f"## {title}", ""]
        for idx, item in enumerate(items, 1):
            lines.extend([
                f"### {idx}. {item.title}",
                f"- 来源: {item.source}",
                f"- URL: {item.url}",
                f"- 时间: {item.published_at or '未知'}",
                f"- 可信等级: Tier {item.credibility_tier}",
                f"- 可信分: {item.confidence_score}",
                f"- 验证状态: {item.verification_status}",
                f"- 摘要: {item.snippet or '无'}",
            ])
            if item.body_excerpt:
                lines.append(f"- 正文摘录: {item.body_excerpt[:1200]}")
            lines.append("")
        return "\n".join(lines)

    # Helper methods below should be kept small and deterministic.
    def _normalize_cn_ticker(self, ticker: str) -> dict[str, str]:
        raw = str(ticker).strip().upper()
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

    def _time_range_from_dates(self, start_date: str, end_date: str) -> str:
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

    def _domain(self, url: str) -> str:
        return urlparse(url).netloc.lower().removeprefix("www.")

    def _clean_url(self, url: str) -> str:
        parsed = urlparse(url)
        query = [
            (k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
            if not k.lower().startswith(("utm_", "spm", "from", "ref"))
        ]
        return urlunparse(parsed._replace(query=urlencode(query)))

    def _domain_tier(self, domain: str) -> int:
        tier0 = ("cninfo.com.cn", "sse.com.cn", "szse.cn", "bse.cn", "csrc.gov.cn", "pbc.gov.cn", "stats.gov.cn", "ndrc.gov.cn", "mof.gov.cn")
        tier1 = ("stcn.com", "cs.com.cn", "cnstock.com", "cls.cn", "yicai.com", "xinhuanet.com", "people.com.cn", "21jingji.com", "caixin.com")
        tier2 = ("eastmoney.com", "finance.sina.com.cn", "stock.finance.sina.com.cn", "finance.qq.com", "money.163.com", "10jqka.com.cn", "hexun.com", "jrj.com.cn")
        tier3 = ("guba.eastmoney.com", "xueqiu.com", "baijiahao.baidu.com", "mp.weixin.qq.com", "zhihu.com", "bilibili.com", "tieba.baidu.com")
        if any(domain.endswith(d) for d in tier0):
            return 0
        if any(domain.endswith(d) for d in tier1):
            return 1
        if any(domain.endswith(d) for d in tier2):
            return 2
        if any(domain.endswith(d) for d in tier3):
            return 3
        return 9

    def _source_score(self, tier: int) -> float:
        return {0: 1.0, 1: 0.85, 2: 0.68, 3: 0.35}.get(tier, 0.45)

    def _freshness_score(self, published_at: str | None) -> float:
        if not published_at:
            return 0.50
        try:
            dt = datetime.fromisoformat(published_at[:10])
            age_days = max((datetime.now() - dt).days, 0)
        except Exception:
            return 0.50
        if age_days <= 1:
            return 1.0
        if age_days <= 3:
            return 0.8
        if age_days <= 7:
            return 0.65
        if age_days <= 30:
            return 0.45
        return 0.25

    def _completeness_score(self, item: NewsItem) -> float:
        has_time = bool(item.published_at)
        has_body = bool(item.body_excerpt)
        has_snippet = bool(item.snippet)
        if has_body and has_time:
            return 1.0
        if has_body:
            return 0.8
        if has_snippet and has_time:
            return 0.65
        if has_snippet:
            return 0.55
        return 0.35

    def _cluster_by_title(self, items: list[NewsItem]) -> dict[str, list[NewsItem]]:
        clusters: dict[str, list[NewsItem]] = {}
        for item in items:
            key = re.sub(r"\W+", "", item.title.lower())[:40]
            clusters.setdefault(key, []).append(item)
        return clusters

    def _corroboration_score(self, item: NewsItem, clusters: dict[str, list[NewsItem]]) -> float:
        if item.credibility_tier == 0:
            return 1.0
        key = re.sub(r"\W+", "", item.title.lower())[:40]
        domains = {x.source for x in clusters.get(key, []) if x.source}
        trusted_domains = {x.source for x in clusters.get(key, []) if x.credibility_tier in (1, 2)}
        if len(trusted_domains) >= 2:
            return 0.85
        if item.credibility_tier in (1, 2):
            return 0.55
        if len(domains) >= 2:
            return 0.45
        if item.credibility_tier == 3:
            return 0.20
        return 0.35

    def _verification_status(self, item: NewsItem, clusters: dict[str, list[NewsItem]]) -> str:
        if item.credibility_tier == 0:
            return "official_verified"
        key = re.sub(r"\W+", "", item.title.lower())[:40]
        trusted_domains = {x.source for x in clusters.get(key, []) if x.credibility_tier in (1, 2)}
        if len(trusted_domains) >= 2:
            return "multi_source_verified"
        if item.credibility_tier == 1:
            return "trusted_media"
        if item.credibility_tier == 2:
            return "mainstream_portal"
        if item.credibility_tier == 3:
            return "social_or_unverified"
        return "unverified"

    def _normalize_date(self, value: Any) -> str | None:
        if not value:
            return None
        text = str(value).strip()
        # Keep this permissive because SearXNG engines return mixed date formats.
        match = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", text)
        if match:
            y, m, d = match.groups()
            return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
        return text[:32]

    def _dedupe_items(self, items: list[NewsItem]) -> list[NewsItem]:
        seen: set[str] = set()
        deduped: list[NewsItem] = []
        for item in items:
            key = hashlib.sha1(f"{item.title}|{item.url}".encode("utf-8")).hexdigest()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    def _cache_key(self, query: str, time_range: str) -> str:
        return hashlib.sha1(f"{self.mode}|{query}|{time_range}".encode("utf-8")).hexdigest()

    def _get_cache(self, key: str) -> list[NewsItem] | None:
        cached = self._cache.get(key)
        if not cached:
            return None
        ts, value = cached
        if time.time() - ts > self.cache_ttl:
            self._cache.pop(key, None)
            return None
        return value

    def _set_cache(self, key: str, value: list[NewsItem]) -> None:
        self._cache[key] = (time.time(), value)
```

重要适配说明：

- 上面代码是推荐实现骨架。Codex 必须根据本地 `BaseMarketDataProvider` 的构造方式和方法签名进行适配。
- 如果项目不允许 provider 自己创建 `requests.Session()`，则改用项目已有 HTTP 工具。
- 如果项目没有 `bs4` 依赖，优先检查依赖文件；如果没有，应添加 `beautifulsoup4`，或改用标准库 `html.parser` 做最小抽取。

---

## 十三、需要修改的文件

### 13.1 注册 provider

文件：

```text
tradingagents/dataflows/providers/registry.py
```

目标：

```python
from .cn_searxng_provider import CnSearxngProvider
```

在 provider 注册表中加入：

```python
"cn_searxng": CnSearxngProvider
```

具体代码以本地 registry 结构为准。

### 13.2 默认配置

文件：

```text
tradingagents/default_config.py
```

新增配置：

```python
"searxng_base_url": os.getenv("SEARXNG_BASE_URL", "http://127.0.0.1:8888"),
"searxng_mode": os.getenv("SEARXNG_MODE", "balanced"),
"searxng_timeout": int(os.getenv("SEARXNG_TIMEOUT", "8")),
"searxng_fetch_body": os.getenv("SEARXNG_FETCH_BODY", "true").lower() in ("1", "true", "yes", "on"),
"searxng_max_results": int(os.getenv("SEARXNG_MAX_RESULTS", "16")),
"searxng_min_score": float(os.getenv("SEARXNG_MIN_SCORE", "0.45")),
"searxng_cache_ttl_seconds": int(os.getenv("SEARXNG_CACHE_TTL_SECONDS", "900")),
```

修改新闻源优先级：

```python
"news_data": "cn_searxng,cn_akshare,yfinance"
```

如果本地配置使用列表：

```python
"news_data": ["cn_searxng", "cn_akshare", "yfinance"]
```

### 13.3 依赖

检查：

```text
pyproject.toml
requirements.txt
requirements-dev.txt
```

如果没有以下依赖，添加：

```text
beautifulsoup4
requests
```

如果项目已使用 `httpx`，可以不用 `requests`，把 provider 改成 `httpx`。

### 13.4 环境变量模板

如果项目有 `.env.example`，添加：

```env
SEARXNG_BASE_URL=http://127.0.0.1:8888
SEARXNG_MODE=balanced
SEARXNG_TIMEOUT=8
SEARXNG_FETCH_BODY=true
SEARXNG_MAX_RESULTS=16
SEARXNG_MIN_SCORE=0.45
SEARXNG_CACHE_TTL_SECONDS=900
```

### 13.5 前端配置，作为可选增强

如果项目已有设置页面，则新增“新闻源设置”：

```text
SearXNG 地址
搜索模式：strict / balanced / broad
是否抓取正文
最大结果数
最低可信分
超时时间
缓存 TTL
```

如果后端已有系统配置 API，则把这些字段保存到现有配置存储中。

如果项目没有配置存储，第一版不要强行重构前端，先用 `.env` 和 `default_config.py`。

---

## 十四、输出格式要求

`cn_searxng` 返回给上层的新闻文本应类似：

```markdown
## 贵州茅台(600519) SearXNG 新闻

### 1. 贵州茅台发布年度权益分派公告
- 来源: cninfo.com.cn
- URL: https://...
- 时间: 2026-06-07
- 可信等级: Tier 0
- 可信分: 0.94
- 验证状态: official_verified
- 摘要: ...
- 正文摘录: ...
```

如果上层期望列表/JSON，则返回结构化数据，但必须保留同等字段：

```json
{
  "title": "...",
  "url": "...",
  "source": "...",
  "published_at": "...",
  "snippet": "...",
  "body_excerpt": "...",
  "credibility_tier": 0,
  "confidence_score": 0.94,
  "verification_status": "official_verified"
}
```

---

## 十五、测试计划

### 15.1 单元级测试

至少测试：

```text
normalize_cn_ticker("600519")
normalize_cn_ticker("600519.SH")
normalize_cn_ticker("000001.SZ")
domain tier 判断
URL 清洗
去重
评分
空结果
SearXNG 超时
```

### 15.2 本地接口测试

先直接请求 SearXNG：

```powershell
Invoke-RestMethod "http://127.0.0.1:8888/search?q=贵州茅台%20公告&format=json&language=zh-CN&categories=news,general"
```

如果返回 HTML 或报错，先修 SearXNG 配置，不要改项目代码硬绕。

### 15.3 provider 测试

在项目虚拟环境中运行最小测试：

```python
from tradingagents.dataflows.providers.cn_searxng_provider import CnSearxngProvider

p = CnSearxngProvider({
    "searxng_base_url": "http://127.0.0.1:8888",
    "searxng_mode": "balanced",
    "searxng_fetch_body": True,
})

print(p.get_news("600519", "2026-06-01", "2026-06-07"))
print(p.get_global_news("2026-06-07", look_back_days=3, limit=5))
```

### 15.4 集成测试

使用项目已有 CLI 或 Web 分析入口，对一个 A 股代码运行新闻分析：

```text
600519
000001
300750
```

验收标准：

1. 新闻分析不报错。
2. 输出中能看到 `cn_searxng` 来源。
3. 新闻包含 URL、来源、时间、可信分。
4. SearXNG 不通时能自动 fallback 到 AkShare。
5. 抓正文失败时不影响主流程。

---

## 十六、不要做的事

1. 不要让 provider 阻塞整个分析流程。
2. 不要把 Tier 3 社区信息当成事实新闻。
3. 不要无 timeout 抓正文。
4. 不要一次抓几十篇正文。
5. 不要在代码中写死你的云服务器公网地址。
6. 不要把 SearXNG 当权威新闻库；它只是搜索入口。
7. 不要破坏现有 `cn_akshare` 和 `yfinance` provider。
8. 不要改变上层 agent 的输入格式，除非本地代码明确需要。

---

## 十七、交付要求

开发完成后，Codex 应报告：

```text
新增文件
修改文件
默认配置
测试命令
测试结果
已知限制
```

并明确说明：

```text
SearXNG 可提升新闻发现和补充验证能力，但最终可靠性仍取决于上游搜索引擎、新闻源质量、正文抓取成功率和来源分级规则。
```


