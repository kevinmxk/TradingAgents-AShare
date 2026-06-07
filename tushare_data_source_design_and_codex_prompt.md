# TradingAgents-AShare 新增 Tushare 数据源设计文档

本文档用于指导 Codex 在本地 Windows 开发电脑上的 `KylinMountain/TradingAgents-AShare` 项目中开发 `cn_tushare` 数据源。

目标是把 Tushare 接入为一个可配置、可探测权限、可 fallback 的结构化 A 股数据源，而不是简单保存一个 token 后默认全量接管所有数据。

---

## 一、设计结论

Tushare 与 SearXNG 的定位不同：

- SearXNG：新闻搜索和多源发现，适合补充非结构化新闻。
- Tushare：结构化行情、基础资料、复权因子、部分财务数据，适合作为行情/财务类数据源。

因此 `cn_tushare` 应优先覆盖：

```text
历史日线行情
复权行情或复权因子
股票基础资料，在 token 权限允许时
部分基本面/财务接口，在 token 权限允许时
实时行情，作为补充源而不是唯一实时源
```

不建议第一版用 Tushare 接管新闻数据。Tushare 新闻、公告、分钟等接口通常属于单独权限或更高门槛接口，120 积分 token 不应默认假设可用。

---

## 二、官方权限事实与 120 积分边界

开发前必须理解 Tushare 权限模型。

官方文档：

```text
权限说明:
https://tushare.pro/document/1?doc_id=108

积分频次表:
https://www.tushare.pro/document/1?doc_id=290

调取说明与错误码:
https://tushare.pro/document/1?doc_id=40
```

关键事实：

1. Tushare Pro 有积分权限门槛。
2. 积分通常是权限门槛，不是每次调用扣积分。
3. 部分接口按积分开放。
4. 部分接口需要单独开权限，和积分不完全等价，例如分钟数据、新闻舆情、公告等。
5. Tushare API 返回码中，`2002` 表示权限问题。
6. 官方积分频次表显示，120 积分档可访问能力非常有限，至少应假设只能稳定测试股票非复权日线行情。

因此本文档中的 120 积分 token 用于：

```text
验证 token 有效性
验证 daily 日线行情接口
验证 fallback 机制
验证低权限情况下 capability detection 是否正确标记权限不足
```

不要用 120 积分 token 作为财务、每日指标、新闻、公告、分钟数据等完整能力的验收依据。

---

## 三、总体架构

新增 provider：

```text
tradingagents/dataflows/providers/cn_tushare_provider.py
```

新增配置能力：

```text
用户前端设置 -> 后端保存 -> 分析任务合并配置 -> cn_tushare provider 读取 token 和能力状态
```

配置优先级：

```text
前端用户保存配置 > 环境变量 > default_config.py 默认值
```

数据源链路建议：

```python
core_stock_apis = "cn_tushare,cn_akshare,cn_baostock,yfinance"
technical_indicators = "cn_tushare,cn_akshare,cn_baostock"
fundamental_data = "cn_tushare,cn_akshare"
realtime_data = "cn_akshare,cn_tushare"
news_data = "cn_searxng,cn_akshare,yfinance"
```

说明：

- Tushare 可优先用于历史行情。
- 实时行情仍建议 AkShare 优先，Tushare 只做补充。
- 新闻仍建议 SearXNG/AkShare 优先。
- 每个接口必须按 capability detection 决定是否启用，不能因为用户填了 token 就直接调用所有接口。

---

## 四、前端设置设计

新增或扩展“数据源设置”页面，加入 Tushare 区块。

字段：

```text
启用 Tushare: boolean
Tushare Token: password input
Token 状态: 未配置 / 已配置 ****abcd / 无效 / 权限不足
测试连接按钮
检测权限按钮
最近检测时间
检测结果表
```

可选高级配置：

```text
请求超时: 默认 10 秒
每分钟限流: 默认 40 或更低，120 积分测试建议保守
缓存 TTL: 默认 86400 秒
是否启用 Tushare 历史行情
是否启用 Tushare 基本面
是否启用 Tushare 实时行情
```

前端安全要求：

1. Token 输入框使用 password 类型。
2. 后端返回配置时不要返回完整 token。
3. 前端只显示“已配置”和 token 后四位，例如 `********abcd`。
4. Token 不要写入浏览器 localStorage，除非项目现有配置就是这样做且没有后端存储。
5. 保存成功后清空表单中的明文 token。

---

## 五、后端配置存储设计

需要新增或扩展设置 API。

推荐 API：

```text
GET  /settings/data-sources/tushare
POST /settings/data-sources/tushare
POST /settings/data-sources/tushare/test
POST /settings/data-sources/tushare/probe-capabilities
```

如果项目已有统一设置 API，则复用现有 API，不要强行新增一套平行系统。

保存字段建议：

```json
{
  "tushare_enabled": true,
  "tushare_token": "encrypted-or-protected",
  "tushare_timeout": 10,
  "tushare_rate_limit_per_minute": 40,
  "tushare_cache_ttl_seconds": 86400,
  "tushare_capabilities": {
    "token_valid": true,
    "daily": "available",
    "stock_basic": "permission_denied",
    "trade_cal": "permission_denied",
    "adj_factor": "permission_denied",
    "daily_basic": "permission_denied",
    "fina_indicator": "permission_denied",
    "income": "permission_denied",
    "balancesheet": "permission_denied",
    "cashflow": "permission_denied",
    "realtime_quote": "unknown",
    "news": "not_supported_first_version",
    "last_checked_at": "2026-06-07T10:00:00+08:00"
  }
}
```

Token 存储要求：

1. 最好复用项目已有密钥/配置加密能力。
2. 如果没有加密体系，至少不要在日志中打印 token。
3. 如果项目用 JSON 文件保存配置，应限制文件权限，并且后端 API 永远不返回完整 token。
4. `.env` 中的 `TUSHARE_TOKEN` 仍保留为兜底。

---

## 六、能力探测设计

不要只通过“查询积分数”判断权限。更稳妥的方式是做接口探测。

原因：

- 有些接口按积分开放。
- 有些接口单独开权限。
- 文档和账号实际权限可能不完全一致。
- 最可靠的判断是小样本调用接口，看是否返回权限错误、空数据或有效数据。

### 6.1 探测状态枚举

```text
available
permission_denied
rate_limited
invalid_token
empty_result
network_error
server_error
unknown_error
not_configured
not_supported_first_version
```

### 6.2 错误识别

如果 Tushare 返回：

```text
code == 0
```

表示请求成功。

如果返回：

```text
code == 2002
```

表示权限问题，应标记 `permission_denied`。

如果错误消息包含：

```text
权限
积分
抱歉
每分钟最多访问
token
```

应分别归类到权限、限流或 token 问题。

### 6.3 120 积分 token 探测矩阵

用 120 积分 token 做开发测试时，建议至少探测：

```text
daily: 预期可用，用于 token 和行情基本能力验证
stock_basic: 可能无权限，按实际返回记录
trade_cal: 可能无权限，按实际返回记录
adj_factor: 可能无权限，按实际返回记录
daily_basic: 大概率无权限
fina_indicator: 大概率无权限
income: 大概率无权限
balancesheet: 大概率无权限
cashflow: 大概率无权限
realtime_quote: 按实际返回记录
news/anns: 第一版不启用，仅标记 not_supported_first_version
```

### 6.4 小样本探测参数

优先使用固定、流动性强的股票：

```text
600519.SH
000001.SZ
300750.SZ
```

日线行情探测：

```json
{
  "api_name": "daily",
  "params": {
    "ts_code": "600519.SH",
    "start_date": "20240102",
    "end_date": "20240102"
  },
  "fields": "ts_code,trade_date,open,high,low,close,vol,amount"
}
```

股票基础资料探测：

```json
{
  "api_name": "stock_basic",
  "params": {
    "exchange": "",
    "list_status": "L"
  },
  "fields": "ts_code,symbol,name,area,industry,list_date"
}
```

每日指标探测：

```json
{
  "api_name": "daily_basic",
  "params": {
    "ts_code": "600519.SH",
    "trade_date": "20240102"
  },
  "fields": "ts_code,trade_date,turnover_rate,pe,pb,total_mv,circ_mv"
}
```

财务指标探测：

```json
{
  "api_name": "fina_indicator",
  "params": {
    "ts_code": "600519.SH",
    "period": "20231231"
  },
  "fields": "ts_code,end_date,roe,roa,grossprofit_margin,netprofit_margin"
}
```

注意：探测要限制频率，结果缓存至少 24 小时。

---

## 七、cn_tushare_provider 设计

新增文件：

```text
tradingagents/dataflows/providers/cn_tushare_provider.py
```

职责：

1. 读取 token。
2. 判断是否启用。
3. 根据能力探测结果决定可调用接口。
4. 为上层提供项目已有 provider 需要的方法。
5. 请求失败时按项目 fallback 机制降级。

### 7.1 代码转换

实现：

```python
def normalize_to_ts_code(ticker: str) -> str:
    """
    600519 -> 600519.SH
    600519.SH -> 600519.SH
    SH600519 -> 600519.SH
    sh.600519 -> 600519.SH
    000001 -> 000001.SZ
    300750 -> 300750.SZ
    430047 -> 430047.BJ
    """
```

规则：

```text
6 开头 -> SH
0/3 开头 -> SZ
4/8/9 开头 -> BJ
```

### 7.2 日期转换

Tushare 日期通常使用：

```text
YYYYMMDD
```

实现：

```python
def to_tushare_date(date: str | datetime) -> str:
    """
    2026-06-07 -> 20260607
    """
```

### 7.3 请求方式

可以优先使用官方 Python SDK：

```python
import tushare as ts
pro = ts.pro_api(token)
df = pro.daily(...)
```

也可以使用 HTTP API：

```http
POST http://api.tushare.pro
```

建议第一版使用 SDK，因为返回 DataFrame 更贴近项目数据处理。

如果项目不想增加 SDK 依赖，也可以用 HTTP API，便于错误码解析。

### 7.4 依赖

检查：

```text
requirements.txt
pyproject.toml
```

如未安装，新增：

```text
tushare
```

Tushare SDK 会依赖 pandas，因此项目如已有 pandas 则兼容性通常较好。

### 7.5 限流

120 积分测试建议保守：

```text
默认每分钟最多 40 次
遇到限流错误后退避
同一 ticker/date 的结果缓存
```

不要为了 capability probe 一次性打很多接口。

---

## 八、接口覆盖优先级

### 第一阶段：120 积分可测试闭环

必须实现：

```text
token 保存和读取
测试连接
能力探测
daily 历史日线行情
provider 注册
default_config 接入
fallback
```

120 积分重点验收：

```text
daily 可用时 cn_tushare 命中
daily 不可用/权限不足时 fallback 到 cn_akshare/cn_baostock
daily_basic/fina_indicator 等权限不足时被正确标记，而不是报错中断
```

### 第二阶段：更高权限增强

在 capability detection 显示可用时启用：

```text
stock_basic
adj_factor
daily_basic
fina_indicator
income
balancesheet
cashflow
```

### 第三阶段：可选增强

谨慎启用：

```text
realtime_quote
moneyflow
margin_detail
news
anns
minute data
```

新闻和公告优先级不建议高于 SearXNG/官方公告抓取，除非 token 权限明确可用且结果质量验证通过。

---

## 九、配置文件修改

### 9.1 default_config.py

新增配置项：

```python
"tushare_enabled": os.getenv("TUSHARE_ENABLED", "false").lower() in ("1", "true", "yes", "on"),
"tushare_token": os.getenv("TUSHARE_TOKEN", ""),
"tushare_timeout": int(os.getenv("TUSHARE_TIMEOUT", "10")),
"tushare_rate_limit_per_minute": int(os.getenv("TUSHARE_RATE_LIMIT_PER_MINUTE", "40")),
"tushare_cache_ttl_seconds": int(os.getenv("TUSHARE_CACHE_TTL_SECONDS", "86400")),
"tushare_capability_cache_ttl_seconds": int(os.getenv("TUSHARE_CAPABILITY_CACHE_TTL_SECONDS", "86400")),
```

修改数据源优先级时要谨慎。

推荐第一版默认不强行启用：

```python
"core_stock_apis": "cn_akshare,cn_baostock,yfinance"
```

当用户在前端启用 Tushare 后，运行时配置合并为：

```python
"core_stock_apis": "cn_tushare,cn_akshare,cn_baostock,yfinance"
```

如果项目配置系统不支持动态链路，第一版可以在 default_config 里加入：

```python
"core_stock_apis": "cn_tushare,cn_akshare,cn_baostock,yfinance"
```

但 provider 必须在未启用或无 token 时快速不可用，让 fallback 继续。

### 9.2 .env.example

新增：

```env
# Tushare Pro 数据源配置
# 前端设置中保存的 token 优先于环境变量
TUSHARE_ENABLED=false
TUSHARE_TOKEN=
TUSHARE_TIMEOUT=10
TUSHARE_RATE_LIMIT_PER_MINUTE=40
TUSHARE_CACHE_TTL_SECONDS=86400
TUSHARE_CAPABILITY_CACHE_TTL_SECONDS=86400
```

不要在 `.env.example` 中填真实 token。

---

## 十、注册 provider

修改：

```text
tradingagents/dataflows/providers/registry.py
```

加入：

```python
from .cn_tushare_provider import CnTushareProvider
```

注册：

```python
"cn_tushare": CnTushareProvider
```

具体结构以本地 registry 为准。

---

## 十一、后端 API 开发流程

先查项目是否已有设置 API。若有，复用。若没有，新增最小接口。

### 11.1 读取配置

```http
GET /settings/data-sources/tushare
```

返回：

```json
{
  "enabled": true,
  "token_configured": true,
  "token_masked": "********abcd",
  "timeout": 10,
  "rate_limit_per_minute": 40,
  "cache_ttl_seconds": 86400,
  "capabilities": {},
  "last_checked_at": null
}
```

### 11.2 保存配置

```http
POST /settings/data-sources/tushare
```

请求：

```json
{
  "enabled": true,
  "token": "用户输入的新 token，可为空",
  "timeout": 10,
  "rate_limit_per_minute": 40,
  "cache_ttl_seconds": 86400
}
```

规则：

```text
token 为空时不覆盖旧 token，除非另有 clear_token=true
保存后返回 masked token
不返回完整 token
不打印 token
```

### 11.3 测试连接

```http
POST /settings/data-sources/tushare/test
```

逻辑：

1. 使用前端传入 token 或已保存 token。
2. 调用 `daily` 小样本。
3. 返回 token 是否有效、daily 是否可用、错误类型。

### 11.4 能力探测

```http
POST /settings/data-sources/tushare/probe-capabilities
```

逻辑：

1. 使用已保存 token。
2. 依次探测接口矩阵。
3. 记录每个接口状态。
4. 缓存结果。
5. 返回 capability matrix。

---

## 十二、前端开发流程

在现有设置页新增 Tushare 数据源配置区。

UI 结构：

```text
Tushare 数据源
[启用 Tushare] toggle

Token
[********abcd                ] [修改/保存]

高级设置
请求超时
每分钟限流
缓存 TTL

[测试连接] [检测权限]

权限检测结果
接口              状态
daily             可用
stock_basic       权限不足
daily_basic       权限不足
fina_indicator    权限不足
...

推荐状态：
基础日线行情：可启用
财务数据：当前 token 权限不足
新闻数据：第一版不建议启用
```

前端提示文案：

```text
Tushare token 用于结构化行情和财务数据。低积分账号可能只能访问部分接口，系统会自动检测权限并对不可用接口回退到其他数据源。
```

---

## 十三、provider 返回与 fallback 规则

必须遵守项目现有 fallback 机制。

如果：

```text
未启用 Tushare
未配置 token
token 无效
接口无权限
接口限流
请求超时
返回空数据
```

provider 不应中断整个分析流程，应让系统 fallback 到后续数据源。

如果项目现有约定是抛 `NotImplementedError` 触发 fallback，则保持一致。  
如果项目有专门异常或返回空值触发 fallback，则按本地 `interface.py` 实现。

---

## 十四、缓存设计

至少实现内存缓存。

缓存 key：

```text
provider + api_name + ts_code + start_date + end_date + fields
```

TTL：

```text
行情/财务数据: 86400 秒
能力探测: 86400 秒
实时行情: 30-60 秒
```

第一版不必做磁盘缓存，但如果项目已有数据缓存目录，可复用。

---

## 十五、测试计划

### 15.1 直接测试 Tushare token

不要在日志中打印 token。

最小测试：

```python
import tushare as ts

pro = ts.pro_api("你的 token")
df = pro.daily(
    ts_code="600519.SH",
    start_date="20240102",
    end_date="20240102",
    fields="ts_code,trade_date,open,high,low,close,vol,amount",
)
print(df.head())
```

### 15.2 后端测试

```text
保存 token
读取配置，确认不返回完整 token
测试连接
探测权限
```

### 15.3 provider 测试

```python
from tradingagents.dataflows.providers.cn_tushare_provider import CnTushareProvider

p = CnTushareProvider({
    "tushare_enabled": True,
    "tushare_token": "从安全配置读取，不要写进代码",
})

print(p.get_stock_data("600519", "2024-01-02", "2024-01-05"))
```

具体方法名必须按本地 provider 接口调整。

### 15.4 集成测试

测试股票：

```text
600519
000001
300750
```

测试场景：

```text
Tushare token 有效，daily 命中
Tushare token 为空，fallback
Tushare token 错误，fallback
daily_basic 权限不足，记录能力矩阵但不影响 daily
关闭 Tushare 开关，完全不调用 Tushare
```

---

## 十六、验收标准

必须满足：

1. 用户可以在前端填写 Tushare token 并保存。
2. 后端不返回完整 token。
3. 可以测试 token 和 daily 基础能力。
4. 可以探测并展示接口权限矩阵。
5. `cn_tushare` provider 已注册。
6. `cn_tushare` 可进入数据源链路。
7. 120 积分 token 下，权限不足接口不会导致系统崩溃。
8. Tushare 不可用时能 fallback 到 AkShare/BaoStock/YFinance。
9. `.env.example` 有兜底配置说明。
10. 日志不泄露 token。

---

## 十七、已知限制

第一版需要明确告诉用户：

```text
120 积分 token 只能用于基础测试，不能代表完整 Tushare 能力。
财务、每日指标、新闻、公告、分钟数据等接口可能需要更高积分或单独权限。
Tushare 实时行情不应作为交易级唯一实时行情源。
能力探测结果会缓存，权限变更后可能需要手动重新检测。
```


