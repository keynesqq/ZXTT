# 已打包模块说明（PM 细改版）

> 以 **`run.py` 现有命令** 为准；库内其它代码可 import，但无 CLI。  
> 更新：2026-06-10（8 个基础模块）

---

## 总览

| 模块 | 命令 | 用途一句话 |
|------|------|------------|
| 财联社 `cls` | `python run.py cls collect --articles` | 采财联社看盘 + 五篇固定收评长文 |
| 行情查询 `quote` | `python run.py quote query` | 即时查全字段行情，分层落盘（事实+板块归属） |
| 公告查询 `announcement` | `python run.py announcement query` | 即时查公告，查完落盘 |
| 集合竞价 `auction` | `python run.py auction` | 传入股票列表，竞价时段定时采走势 |
| 资讯查询 `news` | `python run.py news query` | 即时查资讯/观点/研报/行业，查完落盘 |
| **大盘短线生态** `ecosystem` | `python run.py ecosystem collect` | 东财三池 + 汇总 + 池子参考分（**非**最终大盘情绪） |
| **指数快照** `index` | `python run.py index collect` | 上证/深证/创业板等涨跌与量能，独立事实源 |
| **大盘资金流** `flow` | `python run.py flow collect` | 北向 + 大盘主力 + 行业 TOP + 自选主力（可关，默认开） |

技术细节（接口签名、字段表）见各子目录；本文面向**怎么用、产出什么**。

**命名说明：** 产品名 **大盘短线生态**；命令 **`ecosystem collect`**（`market collect` 为兼容别名）。落盘路径暂保留 `data/market_sentiment/` 以兼容老 schema。

**CLI 范围：** 上表 8 个命令即 `run.py` 全部子命令。无 `collect evening` / `collect health` / `feeds collect` / `quote snapshot` 等编排命令。

**盘后建议顺序（手动）：**

```bash
python run.py ecosystem collect
python run.py cls collect --articles
python run.py index collect
python run.py flow collect
```

非交易日各命令加 `--force --date YYYY-MM-DD`。

---

## 1. 财联社 `cls`

### 做什么

从财联社网站采集两类内容：

- **A 层（看盘）**：市场情绪、风口板块、主线等结构化数据，供大盘研判。
- **B 层（五篇长文）**：每个交易日固定五篇栏目文章全文（含正文，非仅链接）。

五篇固定栏目：

| 栏目 | 识别方式 |
|------|----------|
| 每日收评 | 标题以 `【每日收评】` 开头 |
| 数据看盘 | 标题以 `【数据看盘】` 开头 |
| 焦点复盘 | 标题以 `【焦点复盘】` 开头 |
| 当日涨停分析 | `M月D日涨停分析` 或 `【当日涨停分析】` 等 |
| 今日投资舆情热点 | `今日投资舆情热点` 或 `【今日投资舆情热点】` 等 |

### 怎么做的

**代码位置：** `packages/market/cls/`

| 子模块 | 职责 |
|--------|------|
| `finance.py` | A 层看盘 API |
| `daily_articles.py` | B 层五篇发现 + 正文拉取 |
| `request.py` | 财联社签名、HTTP |
| `collect.py` | 编排 A/B 落盘 |

**采集策略（已优化）：**

1. **主路径**：并行请求栏目 Subject API（尤其 `subject_id=1103` 盘面直播），秒级拿到候选。
2. **标题匹配**：按上表规则锁定五篇 ID。
3. **兜底**：仅在已知 ID 附近小范围补扫（≤20），**不再盲扫 400 个 ID**。
4. **正文**：并行拉 `detail/{id}` 页面，解析正文写入 JSON。
5. **默认关闭 AI 匹配**（`cls_articles_use_ai: false`），避免慢且不稳定。

**落盘：**

- A 层：`data/cls_finance/{trade_date}.json`
- B 层：`data/cls_articles/{trade_date}.json`

### 如何使用

```bash
# 仅 A 层看盘
python run.py cls collect

# A + B 五篇长文（通常 20:00 后才有齐）
python run.py cls collect --articles

# 指定日期 / 忽略交易日与晚间限制
python run.py cls collect --articles --force --date 2026-06-09
```

**相关配置**（`config.yaml` → `market` 段）：

| 键 | 含义 | 建议 |
|----|------|------|
| `cls_enabled` | 总开关 | `true` |
| `cls_articles_enabled` | B 层开关 | `true` |
| `cls_articles_after` | B 层最早采集时刻 | `"20:00"` |
| `cls_articles_use_ai` | AI 辅助匹配 | `false` |

**验收标准：**

- 终端 `articles_found: 5`、`articles_ok: true`
- 打开 `data/cls_articles/{date}.json`，五篇均有 `content` 字段
- 全流程约数秒（非分钟级）

---

## 2. 行情查询 `quote query`

### 做什么

按股票代码**即时查询行情**，查完**自动落盘**。支持：

- 单只股票
- 多只股票（逗号分隔）
- 全自选（同花顺配置板块内全部股票）

返回 **46 个字段**（现价、高低价、换手、均线、涨跌停状态、PE 等），与老项目 ZXReport 全量快照字段对齐。

**落盘：** `data/quote_query_{日期}.json`（**schema v2 分层**）

| 字段 | 含义 |
|------|------|
| `quotes` | 事实层：按 **code 去重**，只查一次（如 31 条） |
| `memberships` | 结构层：板块归属行（同股多板块可重复，如 35 行） |
| `structure.groups` | 按 config 板块顺序的分组索引 |
| `code_count` / `row_count` | 不重复只数 / 板块归属行数 |

查前对同花顺自选 **按 code 去重** 拉行情；终端含 `code_count`、`row_count`、`groups`（板块名顺序与 config 一致）、`path`。

**不做的事：** 不写 `data/snapshot_{date}.json`（库内 `packages/quote/snapshot/` 供 query 构建字段，无独立 CLI）。

### 怎么做的

**代码位置：** `packages/quote/`

| 组件 | 职责 |
|------|------|
| `query.py` | 对外 `query_quotes()` |
| `query_cache.py` | 分层落盘、`load_joined_quote_rows()` |
| `snapshot/build.py` | 双源合并、字段 enrich |
| `ths.py` / `tencent.py` | 同花顺主源 + 腾讯辅源 |
| `industry_cache.py` | 行业缓存（复用老项目 `D:\ZXReport\data\industry_cache.json`） |

**数据流：**

1. 读同花顺自选；**事实层**按 code 去重，**结构层**保留全部板块行。
2. 并行拉同花顺 realhead + K 线衍生、腾讯批量行情（内部按 unique code 批量请求）。
3. 合并双源，计算涨跌停、板块、均线等。
4. **查询时不联网补行业**（保证速度）；行业读缓存，缺失可为空。

**与老项目关系：** 数据源、字段与老项目一致；新项目行业缓存为空时会自动合并老项目缓存。

### 如何使用

```bash
# 单股
python run.py quote query --codes 600519

# 多股
python run.py quote query --codes 600519,000001,300750

# 全自选（config 里 analyze_blocks 白名单板块）
python run.py quote query --all
```

**参数说明：**

| 参数 | 含义 |
|------|------|
| `--codes` | 逗号分隔代码，一只或多只 |
| `--all` | 查全部自选（与 `--codes` 互斥） |
| `--date` | 落盘文件名日期（默认今天；**不改变**行情数据源日期） |

**返回：** 终端 JSON，`outcome: ok`，`quotes` 为事实层（不重复 code）；`code_count` / `row_count` 分别为不重复只数与板块行数；成功落盘时有 `path`（文件内另有 `memberships`、`structure`）。

**按板块看行情：** 用 `load_joined_quote_rows()` 或 `join_quotes_with_memberships(quotes, memberships)` 拼成板块行（与 snapshot 口径一致）。

**验收标准：**

- `outcome: ok`；`--all` 时 `code_count` = 不重复只数，`row_count` = 板块归属行数
- 单股能看到 `price`、`pct_chg`、`ma5`、`limit_status` 等
- 全自选冷启动约 1～2 秒（31 只事实，网络只拉 31 code）
- 打开 `data/quote_query_{date}.json`：`schema_version: 2`；`quotes` 与 `memberships`/`structure` 条数分别等于 `code_count`/`row_count`
- **已验（2026-06-10）**：31 只 / 35 行板块；`load_joined_quote_rows()` join 后 35 行

**注意：** `quote query` 落盘 `data/quote_query_{date}.json`（schema v2）；与库内 `write_snapshot_cache()`（`data/snapshot_{date}.json`）不是同一路径，后者当前无 CLI。

---

## 3. 公告查询 `announcement query`

### 做什么

按股票代码**即时查询公告**，查完**自动落盘**。支持：

- 单只股票
- 多只股票（逗号分隔）

返回每条公告的标题、日期、链接、类型等；数据源与老项目一致（**巨潮主源 + AkShare 东财兜底**）。

**落盘：** `data/announcement_query_{日期}.json`（同日按 `code` 合并；成功落盘时终端含 `path`）

**不做的事：**

- 不写 `feeds_cache`、不调用 `feeds/collect.py` 批量函数
- 不查研报、资讯、观点、行业资讯

### 怎么做的

**代码位置：** `packages/announcement/`、`packages/feeds/announcements.py`

| 组件 | 职责 |
|------|------|
| `announcement/query.py` | 对外 `query_announcements()` |
| `announcement/query_cache.py` | 落盘 `announcement_query_{日}.json` |
| `feeds/announcements.py` | 巨潮 + AkShare 拉取（query 与库批量函数共用） |
| `feeds.cninfo` / `feeds.eastmoney` | 数据源 HTTP / AkShare |

**查询流程：**

1. 解析并去重代码；在自选里的保留名称/分组。
2. **2 只及以上并行**拉取（worker 数读 `feeds.max_workers`，默认 4）。
3. 调用 `fetch_announcement_rows`：巨潮 → AkShare（时间范围内）。
4. **默认不兜底**历史最新条；范围内无公告则空列表 + 提示「近 N 日内无公告」。
5. 传 `--latest N` 才启用历史最新 N 条兜底（与 `feeds/collect.py` 批量函数行为一致）。

### 如何使用

```bash
# 单股（天数/条数读 config）
python run.py announcement query --codes 600519

# 多股
python run.py announcement query --codes 600519,000001,300750

# 临时指定：近 7 天、最多 10 条、兜底 3 条
python run.py announcement query --codes 600519 --days 7 --max-count 10 --latest 3

# 全自选 31 只、近一周（并行，约 4 秒）
python run.py announcement query --codes 000021,000066,... --days 7
```

**参数说明：**

| 参数 | 含义 |
|------|------|
| `--codes` | 逗号分隔代码（必填） |
| `--days` | 回溯天数（默认 `feeds.announcement.lookback_days`） |
| `--max-count` | 最多返回条数，0=不限制（默认 `max_count`） |
| `--latest` | 启用历史最新 N 条兜底（**不传则不兜底**） |
| `--date` | 回溯截止日期（默认今天） |

**相关配置**（`config.yaml` → `feeds.announcement`）：

| 键 | 含义 | 建议 |
|----|------|------|
| `lookback_days` | 默认回溯天数 | `3` |
| `fallback_latest_count` | 仅 `feeds/collect.py` 批量函数用；**query 不传 `--latest` 时不读** | `3` |
| `max_count` | 默认最多条数（0=不限） | `0` |
| `fallback` | 巨潮失败时是否用 AkShare | `akshare` |

**验收标准：**

- `outcome: ok`，`count` 等于传入代码数
- 每只 `items[]` 含 `announcements`，字段含 `title`、`pub_date`、`url`
- 改 `--days` / `--max-count` 后返回条数随之变化
- **已验（2026-06-10）**：31 只自选、`--days 7` → **66 条**公告，约 **6 秒**
- 打开 `data/announcement_query_{date}.json`，`items` 与终端一致

---

## 4. 集合竞价 `auction`

### 做什么

**开盘辅助分析**：你提供个股列表，模块在集合竞价时段（默认 **9:15:05–9:25:05**）每 **30 秒**拉一次轻量行情，最后汇总每只股的竞价走势。

**核心产出：** 每只股票在竞价期间的缺口变化形态（如「一路抬升」「冲高回落」），以及 9:20 后更可信的形态、涨跌停状态等。

**不做的事：**

- 不读同花顺自选板块（除非你通过 `--codes` 或 config 显式传入）
- 不包含 feeds、全量行情、财联社等其它采集
- 不提供五档盘口、撤单明细（免费行情无此数据）

### 怎么做的

**代码位置：** `packages/auction/`

| 组件 | 职责 |
|------|------|
| `watch.py` | 定时调度、循环采样 |
| `stocks.py` | 解析用户代码列表；读 config 默认列表 |
| `series.py` | 写入时间序列 `auction_series_{date}.json` |
| `trajectory.py` | 汇总走势 `auction_trend_{date}.json` |
| `packages/quote/auction_snap.py` | 竞价轻量行情（仅 realhead，不拉 K 线；由 auction 模块 import） |

**采样流程：**

1. 解析代码（CLI `--codes` 优先，否则 `config.yaml` → `auction.codes`）；同代码只保留一条。
2. 非 `--force` 时：等到每个计划时刻（21 个点），拉行情写入 series。
3. `--force` 时：立即采 1 个点（验通路用，形态为「数据不足」属正常）。
4. 结束后计算 `auction_trend`：
   - `shape`：全程形态
   - **`shape_after_920`**：9:20 后形态（**开盘判断优先看这个**）
   - `gap_path` / `end_gap`：缺口曲线与最终缺口
   - `amount_delta_path`：相邻采样成交额增量
   - `limit_status`：末点涨跌停状态

**落盘：**

| 文件 | 说明 |
|------|------|
| `data/auction_trend_{date}.json` | **主产出**，开盘分析看这个 |
| `data/auction_series_{date}.json` | 原始采样点（内部/debug） |
| `data/last_auction_watch.json` | 最近一次运行状态 |

### 如何使用

```bash
# 指定股票（一只或多只）
python run.py auction --codes 600519
python run.py auction --codes 600519,000001,300750

# 用 config 默认列表（计划任务常用）
python run.py auction

# 快速验通路（只采 1 点，不等 10 分钟）
python run.py auction --force --codes 600519,000001

# 离线模拟（无网络，开发验收）
python run.py auction --simulate --date 2026-06-10
```

**配置**（`config.yaml` → `auction` 段）：

```yaml
auction:
  interval_sec: 30
  watch_start: "09:15:05"
  watch_end: "09:25:05"
  codes:          # 计划任务可不传 --codes
  - "600519"
  - "000001"
```

**计划任务：** `scripts/run_auction_watch.bat` → 执行 `python run.py auction`（需在 config 配好 `codes`）。

**验收标准：**

| 场景 | 预期 |
|------|------|
| `--force` + 31 只 | 约 1 秒内，`stock_count: 31`，均有 `end_gap` |
| 交易日完整跑 | 约 10 分钟（等时钟），`point_count: 21`，`shape_after_920` 非「数据不足」 |
| `--simulate` | `outcome: ok`，生成 trend + series |

**竞价分析要点对照：**

| 关注点 | trend 字段 |
|--------|------------|
| 开盘缺口 | `start_gap`、`end_gap`、`gap_path` |
| 9:20 后可信走势 | `shape_after_920` |
| 竞价是否放量 | `amount_delta_path` |
| 接近涨跌停 | `limit_status` |

---

## 5. 资讯查询 `news query`

### 做什么

按股票代码**即时查询非公告文字素材**，查完**自动落盘**。四类：

- **news** — 个股新闻
- **opinions** — 券商/媒体短评（由资讯标题规则分类）
- **research** — 卖方研报
- **industry_news** — 所属行业相关新闻

**落盘：** `data/news_query_{日期}.json`（同日按 `code` 合并；成功落盘时终端含 `path`）

**不做的事：**

- 巨潮公告 → `announcement query`
- 价量/均线 → `quote query`
- 财联社长文 → `cls collect`
- 竞价走势 → `auction`

### 怎么做的

**代码位置：** `packages/news/`、`packages/feeds/non_announcement.py`

| 组件 | 职责 |
|------|------|
| `news/query.py` | 对外 `query_news()`，多股并行 |
| `news/query_cache.py` | 落盘 `news_query_{日}.json` |
| `feeds/non_announcement.py` | 四类采集共用（news query 与库批量函数复用） |
| `feeds/eastmoney.py` | 东财 AkShare 主源 |
| `feeds/ths_f10.py` | 同花顺 F10 兜底（`on_empty` 时） |

**查询流程：**

1. 解析代码；批量读本地行业缓存。
2. **2 只及以上并行**（worker 数读 `news.max_workers`，示例配置 **8**）。
3. 单股内 **研报 / 资讯观点 / 行业** 并行拉取；资讯按股票名+代码双关键词并行。
4. 同批 **相同行业名只拉 1 次** 行业资讯，结果复用到各股。
5. 主源东财；资讯/研报空时可选同花顺兜底（`--strict` 时关闭兜底与 STALE 提示）。

### 如何使用

```bash
# 单股（默认近 3 天、四类全查）
python run.py news query --codes 600519

# 多股
python run.py news query --codes 600519,000001,300750

# 批量扫自选：严格窗口、不要过期兜底
python run.py news query --codes 600519,000001 --days 3 --strict

# 只要新闻+观点（少一半请求）
python run.py news query --codes 600519 --categories news,opinions

# 跳过行业资讯
python run.py news query --codes 600519 --no-industry
```

**参数说明：**

| 参数 | 含义 |
|------|------|
| `--codes` | 逗号分隔代码（必填） |
| `--days` | 四类共用回溯天数（默认 `news.lookback_days`，3） |
| `--max-count` | 每类独立上限，0=不限 |
| `--categories` | `news,opinions,research,industry` 子集 |
| `--no-industry` | 不查行业资讯 |
| `--date` | 回溯截止日期（默认今天） |
| `--strict` | 严格窗口：窗口外不展示、不用同花顺兜底、无 STALE 提示 |

**相关配置**（`config.yaml` → `news` 段）：

| 键 | 含义 | 建议 |
|----|------|------|
| `lookback_days` | 默认回溯天数 | `3` |
| `max_workers` | 多股并行数（≤16） | `8`（过高易东财限流） |
| `akshare_timeout_sec` | 单次 AkShare 超时 | `45` |
| `industry_enabled` | 是否查行业资讯 | `true` |
| `ths_f10.enabled` | 是否启用同花顺兜底 | `true` |

**验收标准：**

- `outcome: ok`，`count` 等于传入代码数
- 每股含 `news` / `opinions` / `research` / `industry_news`，**无** `announcements`
- `--strict` 时窗口外条目不出现
- **已验（2026-06-10）**：31 只自选、`--strict --days 3` → 新闻 53、观点 35，约 **14 秒**
- 打开 `data/news_query_{date}.json`，`items` 与终端一致

---

## 6. 大盘短线生态 `ecosystem`

### 模块命名

| 口径 | 名称 |
|------|------|
| **产品名** | 大盘短线生态 |
| **命令 slug** | `ecosystem` |
| **命令** | `python run.py ecosystem collect`（`market collect` 为兼容别名） |
| **不是** | 财联社 `cls`、最终「大盘情绪」结论、AI 解读 |

**一句话：** 从东财拉**涨停池 / 炸板池 / 昨涨停池**，汇总打板结构事实，并给出**仅基于三池的参考分**（`pool_*`），供与财联社**相互印证**；**不在本模块内产出最终大盘情绪**。

### 做什么

**采集层 · 交易结构侧**（与 cls 的媒体/叙事侧并列）：

| 层级 | 内容 |
|------|------|
| **三池事实** | 今日涨停、今日炸板、昨日涨停今日表现（溢价） |
| **结构汇总** | 家数、均涨幅、炸板修复、最高连板、2 板+、行业 TOP、连板龙头 |
| **池子参考分** | `pool_score` / `pool_signal` / `pool_hint` — 仅 AkShare 三池规则，**非**最终情绪 |
| **下游索引** | `limit_up_index` — 供下游报告/库代码补连板字段 |

**不做的事：**

- 财联社看盘、五篇长文 → `cls collect`
- 用 cls 数据参与本模块打分或写入本模块 JSON
- 综合 cls + 生态 → **「大盘情绪」**（属**解读层**，报告期再做）
- 指数涨跌、北向资金等 → 后续独立模块（见下文「印证扩展」）

### 与 cls、大盘情绪的关系

```
采集（本模块负责）              采集（cls 模块）           解读（不在采集里）
─────────────────              ────────────────           ─────────────────
market_sentiment/{日}.json     cls_finance/{日}.json
  · 三池 + 汇总 + pool_*   ←→   · 热度/封板率/风口…    →   相互印证 → 大盘情绪
  · 无 cls 字段                cls_articles/{日}.json
                                 · 五篇收评长文
```

**典型印证（解读层规则示例，实现后做）：**

| 生态侧 | cls 侧 | 含义 |
|--------|--------|------|
| `limit_up_count` / 炸板家数 | `seal_rate`、涨停/跌停家数 | 总量是否一致 |
| `prev_limit_avg_pct` | `prev_zt_performance` | 昨涨停溢价互证 |
| `hot_industries` | `wind_plates` / 主线 | 主线是否被池子证实 |
| `pool_signal` 与 cls 热度背离 | — | 降档或标 warn |

### 怎么做的

**代码位置：** `packages/market/sentiment.py`（整包迁移自老项目；与 `packages/market/cls/` **代码目录分离**）

| 步骤 | 说明 |
|------|------|
| 1 | AkShare 东财：`stock_zt_pool_em`（涨停）、`stock_zt_pool_zbgc_em`（炸板）、`stock_zt_pool_previous_em`（昨涨停） |
| 2 | 汇总家数、溢价、修复率、连板高度、行业集中度 |
| 3 | `_score_pool` 仅读三池 → 写入 `pool_score` / `pool_signal` / `pool_hint`（双写 `emotion_*` 兼容旧读盘） |
| 4 | 写 manifest 源 `akshare_zt_pool`；三池皆空 → `ok=false` |
| 5 | **不调用** cls 模块；五篇长文请单独 `python run.py cls collect --articles` |

**打包状态：** 已验收（2026-06-10）。与 cls 代码目录分离，JSON 互不嵌套。

### 如何使用

```bash
# 采三池 + 汇总 + pool 参考分（交易日；非交易日加 --force）
python run.py ecosystem collect --force --date 2026-06-09

# 兼容别名
python run.py market collect --force --date 2026-06-09
```

**勿在本命令使用 `--articles`**（财联社长文请用 `cls collect --articles`；`--articles` 将废弃）。

**相关配置**（`config.yaml` → `market` 段）：

| 键 | 含义 | 建议 |
|----|------|------|
| `enabled` | 生态采集总开关 | `true` |

超时读 `feeds.akshare_timeout_sec`（与 feeds/market 共用）。`cls_enabled` 等 cls 键见 **§1 财联社**。

### 产出

**主文件：** `data/market_sentiment/{trade_date}.json`

| 字段组 | 代表字段 |
|--------|----------|
| 家数 | `limit_up_count`、`broken_limit_count`、`prev_limit_count` |
| 溢价/修复 | `prev_limit_avg_pct`、`prev_limit_premium_3pct`、`broken_limit_repair_count` |
| 结构 | `max_consecutive_boards`、`boards_2plus`、`hot_industries`、`limit_up_leaders` |
| 池子参考分 | `pool_score`、`pool_signal`、`pool_hint` |
| 索引 | `limit_up_index`、`broken_limit_index` |
| 元数据 | `date`、`calendar_date`、`collected_at_iso`、`warnings` |

**验收标准：**

- 终端 `outcome: ok`，含 `limit_up_count`、`pool_signal`
- JSON **无** `cls` 块；含 `pool_score` / `pool_hint`
- manifest → `sources.akshare_zt_pool.ok` 为 true（三池非全空）
- **已验（2026-06-10）**：`ecosystem collect --force --date 2026-06-09` → 涨停 **130**、炸板 **24**、`pool_signal` **中**（71 分）；JSON 无 `cls`；单测 14 条 OK

---

## 7. 指数快照 `index`

### 模块命名

| 口径 | 名称 |
|------|------|
| **产品名** | 指数快照 |
| **命令 slug** | `index` |
| **命令** | `python run.py index collect` |
| **不是** | 财联社 cls（页面顶部指数未走 emotion 接口）、最终「大盘情绪」、个股行情 |

**一句话：** 腾讯 qt 拉**上证 / 深证成指 / 创业板 / 中证500** 等点位与涨跌幅，作为大盘涨跌的**独立事实源**，供与 cls、生态**印证**（如「指数红、情绪弱」）。

### 做什么

**采集层 · 指数事实侧**（与 cls 叙事、生态打板结构并列）：

| 层级 | 内容 |
|------|------|
| **点位** | `price`、`open`、`high`、`low`、`pre_close` |
| **涨跌** | `change`（涨跌额）、`pct_chg`、`open_gap_pct` |
| **量能** | `volume`、`amount_yi`、`turnover`、`amplitude` |
| **时效** | `snapshot_at`（行情时刻，非采集时刻） |
| **阶段** | `pct_5d`/`pct_20d`、`high_52w`/`low_52w`、`pct_ytd` 等 |
| **多时段** | `snapshots[]` 按 `--slot` 保留；顶层 `indices` 为最近一次 |

**落盘：** `data/market_index/{trade_date}.json`

**不做的事：**

- 不采 cls 页面 emotion 里的热度/封板率（→ `cls collect`）
- 不采涨停池结构（→ `ecosystem collect`）
- 不产出最终大盘情绪（解读层综合）

### 与 cls、生态的关系

```
指数快照（本模块）          cls A 层              大盘短线生态
─────────────────          ─────────             ─────────────
market_index/{日}.json     cls_finance/{日}      market_sentiment/{日}
 · 上证/深证/创业板涨跌  ←→  · 热度/成交额叙事  ←→  · 三池 + pool_*
 · 独立行情事实源            · 无三大指数点位        · 无指数涨跌
```

**典型印证（解读层）：** 上证 -0.58% 但 `pool_signal` 偏强 → 指数弱、短线结构尚可；与 cls `rise_count`/`market_heat` 对照防误判。

### 怎么做的

**代码位置：** `packages/market/index_snapshot.py`、`packages/quote/tencent.py`

| 组件 | 职责 |
|------|------|
| `index_snapshot.py` | `collect_market_index()`、`load_market_index()`、`format_index_prompt()` |
| `quote/tencent.py` | `fetch_index_snapshots()`、`fetch_index_open_gaps()`（9:25 开盘环境复用） |

| 步骤 | 说明 |
|------|------|
| 1 | 读 `index.symbols`（默认四指数腾讯代码） |
| 2 | 腾讯 `qt.gtimg.cn` 批量拉行情并解析 |
| 3 | 按 `slot` 合并 `snapshots[]`，写 manifest 源 `tencent_index` |
| 4 | 无数据 → `outcome: warn`，manifest `ok=false` |

**打包状态：** 已验收（2026-06-10）。P0 独立模块，不并入 cls A 层。

### 如何使用

```bash
# 盘后采（默认 slot=evening）
python run.py index collect --force --date 2026-06-10

# 午间 / 早盘多时段（同日合并落盘）
python run.py index collect --force --slot midday --date 2026-06-10
python run.py index collect --force --slot open --date 2026-06-10
```

**参数说明：**

| 参数 | 含义 |
|------|------|
| `--force` | 忽略非交易日检查 |
| `--date` | 日历日（决定 `trade_date` 与文件名） |
| `--slot` | `open` / `morning` / `midday` / `evening` / `manual`（默认 `evening`） |

**相关配置**（`config.yaml` → `index` 段；`market.index_enabled` 为兼容开关）：

| 键 | 含义 | 建议 |
|----|------|------|
| `enabled` | 总开关 | `true` |
| `symbols` | 腾讯代码列表 | `sh000001`、`sz399001`、`sz399006`、`sh000905` |

`config.example.yaml` 已含默认四指数。

### 产出

**主文件：** `data/market_index/{trade_date}.json`

| 字段组 | 代表字段 |
|--------|----------|
| 元数据 | `source`、`trade_date`、`calendar_date`、`latest_slot`、`collected_at_iso` |
| 最新快照 | `indices[]` — `price`、`change`、`pct_chg`、`open_gap_pct`、`volume`、`amount_yi`、`amplitude`、`snapshot_at`、`pct_ytd`、`high_52w` 等 |
| 历史时段 | `snapshots[]` — 每项含 `slot`、`indices` |
| 告警 | `warnings`（采集失败或空数据时） |

解读层拼 prompt：`format_index_prompt(load_market_index(trade_date))`。

**验收标准：**

- 终端 `outcome: ok`，`index_count: 4`
- JSON `indices` 四条，含 `name`、`price`、`pct_chg`
- manifest → `sources.tencent_index.ok` 为 true
- 多 `--slot` 时 `snapshots` 按 `open→morning→midday→evening` 排序保留
- **已验（2026-06-10）**：上证 **3986.66**（**-0.58%**）、深证 **14972.75**（**-1.94%**）、创业板 **3870.83**（**-2.29%**）、中证500 **8052.83**（**-1.51%**）；单测 4 条 OK

---

## 8. 大盘资金流 `flow`

### 模块命名

| 口径 | 名称 |
|------|------|
| **产品名** | 大盘资金流 |
| **命令 slug** | `flow` |
| **命令** | `python run.py flow collect` |
| **不是** | 财联社长文、最终大盘情绪、龙虎榜、个股全字段行情 |

**一句话：** 东财结构化拉 **北向成交净买额 + 大盘主力 + 行业流入/流出 TOP +（可选）自选主力**，独立落盘，供与 cls / 生态 / 指数相互印证。

### 做什么

| 层级 | 内容 | 当日 | 历史 `--date` |
|------|------|------|---------------|
| **L1 北向** | 沪/深股通成交净买额、通道状态 | ✅ | hist 接口 |
| **L2 大盘** | 主力/超大单/大单/中单/小单净流入 | ✅ push2his 合并口径 | 同左 |
| **L3 板块** | 行业流入/流出 TOP N | ✅ | skip + warning |
| **L4 自选** | 配置板块各股当日主力净流入 | ✅ 默认开 | skip + warning |

**参考分 `flow_signal`：** 仅看北向 + 大盘主力，阈值 ±30 亿（强/弱/中）；**不含**涨停家数或 cls 热度。

### 与 cls、生态、指数的关系

```
指数快照              大盘资金流（本模块）           cls A 层
─────────             ──────────────────           ─────────
market_index/         market_flow/
 · 涨跌事实      ←→    · 北向/主力/行业/自选   ←→   · 热度/风口叙事
                       · 独立资金事实源
```

**典型印证（解读层）：** 指数跌 + 主力大幅净流出 + 北向净卖 → 偏空；与 `pool_signal`、cls 热度对照防单源误判。

### 怎么做的

**代码位置：** `packages/market/flow_snapshot.py`、`flow_sources.py`、`flow_eastmoney.py`

| 组件 | 职责 |
|------|------|
| `flow_eastmoney.py` | 东财 httpx 直连：共享会话、请求节流、北向 datacenter、大盘 push2his、行业 clist、自选 **ulist.np 批量** |
| `flow_sources.py` | 直连优先 + AkShare 兜底；字段归一（元→亿元）；L4 批量 → 排行 → AkShare |
| `flow_snapshot.py` | 编排、slot 合并、`flow_score`、落盘、`format_flow_prompt()` |

| 步骤 | 说明 |
|------|------|
| 1 | 读 `flow.enabled`；非交易日需 `--force` |
| 2 | 开共享 httpx 会话；**串行** L1 北向 → L2 大盘（避免并发断连） |
| 3 | L2 盘中读 push2his **当日行**；无当日行则最近一日 + warning |
| 4 | L3 行业 TOP；L4 自选 `ulist.np` 批量（31 只通常 1 次请求） |
| 5 | 写 manifest 源 `akshare_hsgt` / `akshare_market_flow` / `akshare_sector_flow` / `akshare_watchlist_flow` |
| 6 | `--slot` 合并 `snapshots[]` → `data/market_flow/{trade_date}.json` |

**打包状态：** 已验收（2026-06-10）。

### 如何使用

```bash
# 默认：北向 + 大盘 + 行业 TOP + 自选
python run.py flow collect --force --date 2026-06-10

# 跳过自选（更快）
python run.py flow collect --force --no-watchlist

# 午间快照
python run.py flow collect --force --slot midday --date 2026-06-10
```

**参数说明：**

| 参数 | 含义 |
|------|------|
| `--force` | 忽略非交易日检查 |
| `--date` | 日历日 |
| `--slot` | `open` / `morning` / `midday` / `evening` / `manual`（默认 `evening`） |
| `--no-watchlist` | 单次跳过 L4 |
| `--watchlist` | 单次强制拉 L4（覆盖 config 关） |

**相关配置**（`config.yaml` → `flow` 段）：

| 键 | 含义 | 建议 |
|----|------|------|
| `enabled` | 总开关 | `true` |
| `primary` | 主通道 | `eastmoney_direct` |
| `fallback` | 兜底 | `eastmoney_akshare` |
| `watchlist_enabled` | L4 默认开关 | `true` |
| `sector_top_n` | 行业 TOP 条数 | `10` |
| `request_interval_sec` | 东财请求间隔（秒） | `1.0` |
| `stock_batch_size` | 自选 ulist 每批只数 | `50` |

超时复用 `feeds.akshare_timeout_sec`。

### 产出

**主文件：** `data/market_flow/{trade_date}.json`

| 字段组 | 代表字段 |
|--------|----------|
| 北向 | `northbound.net_yi`、`sh_connect_net_yi`、`sz_connect_net_yi`、`connect_status` |
| 大盘 | `market.main_net_yi`、`super_large_net_yi`…、`source_channel`（`push2his`） |
| 板块 | `sectors_inflow_top[]`、`sectors_outflow_top[]` |
| 自选 | `watchlist_flow[]`、`watchlist_enabled` |
| 参考分 | `flow_score`、`flow_signal`、`flow_hint` |
| 多时段 | `snapshots[]` |
| 告警 | `warnings[]`（如无当日 kline 行会说明用了最近一日） |

解读层拼 prompt：`format_flow_prompt(load_market_flow(trade_date))`。

**验收标准：**

- 终端 `outcome: ok`；默认 `watchlist_count` = 自选不重复只数（如 **31**）
- `--no-watchlist` → `watchlist_flow: []`
- JSON **不写入** `market_sentiment` / `cls_finance`
- manifest 四源（L4 关时为 skip）
- **已验（2026-06-10）**：北向 **0** 亿（盘中政策正常）；大盘主力 **+446.8** 亿（push2his）；自选 **31/31** 有 `main_net_yi`；单测 **14** 条 OK

---

## 9. 晚间管线 `evening`（规划中）

> **规格已定稿**，代码与编排 CLI **待实现**。开发主文档：[`evening-dev.md`](evening-dev.md)。

### 做什么

把第 2 步 7 路 raw JSON 经本地预处理（3.1–3.8）收成一份 `evening_context`，再交 AI 出 22 点「明日作战卡」（HTML + 微信简报 + 明日预期）。

### 与八个采集模块的关系

```
quote / announcement / news query  ─┐
ecosystem / cls / index / flow     ─┼→ 第 2 步采集
                                    │
                                    ▼
                         preprocess 3.1–3.8（待实现）
                                    │
                                    ▼
                    evening_context/{date}.json
                                    │
                                    ▼
                         generate 第 4–5 步（待实现）
```

- **分析按 code**（31 只）；**展示按 group**（35 行板块归属）。
- **仅公告+资讯**走指纹增量 reuse；财联社 B 层长文、行情等每日刷新。
- 22:00 跑 `preprocess` 前建议 **重采** `cls collect --articles`（五篇长文常 20:00 后才齐）。

### 规划命令

```bash
python run.py collect --slot evening      # 第 2 步编排（待实现）
python run.py preprocess --slot evening   # 第 3 步 3.1–3.8（待实现）
python run.py generate --slot evening     # 第 4–5 步（待实现）
python run.py generate --slot evening --phase ai      # 仅 AI 研判
python run.py generate --slot evening --phase render  # 仅 HTML/微信
```

五步详文：[`evening-dev.md`](evening-dev.md) §八附录（step1–5 · config · schemas · runbook）。

### 主产出（实现后）

| 路径 | 说明 |
|------|------|
| `data/evening_context/{date}.json` | 第 4/5 步读入 |
| `data/scheduled_ai/evening_{date}.json` | 第 4 步写、第 5 步读 |
| `data/expectations/{date}.json` | 明日预期（按 code） |
| `reports/{date}/daily_evening.html` | 第 5 步 HTML |
| `data/last_report.json` | 最近一次报告路径 |
| `data/ai_digest/{date}/` | 个股 feeds + 财联社 cls digest |
| `data/evening_baseline/{date}.json` | 公告资讯指纹基准 |

---

## 八个模块的关系

```
早盘 9:15                    盘中/盘后
    │                            │
    ▼                            ▼
 auction                 quote / announcement / news query
 (指定股竞价)              (随时查行情 / 公告 / 资讯)
    │                            │
    └──────────────┬─────────────┘
                   ▼
         盘后批量（报告/data 链路）
    ┌──────────────┼──────────────┬──────────────┐
    ▼              ▼              ▼              ▼
 ecosystem      cls collect     index collect   flow collect
 (三池+pool_*)   (--articles)    (主要指数)      (北向/主力/行业/自选)
    │              │              │              │
    └──────┬───────┴──────────────┴──────────────┘
           ▼
    【解读层 · 非本仓库 CLI】大盘情绪 = 多源印证 + 总结
```

- **ecosystem**：结构事实 + 池子参考分，与个股列表无关。  
- **cls**：媒体侧热度、风口、五篇长文。  
- **index**：指数涨跌事实，防「指数红、情绪弱」。  
- **flow**：北向/主力/行业/自选资金事实，与指数、生态对照。  
- **auction / quote / announcement / news**：个股维度；`quote query` 为分层落盘，join 用 `load_joined_quote_rows()`；不参与大盘 JSON 嵌套。

---

## 库代码（无 CLI）

以下在 `packages/` 内可被 import 或供 query 复用，**`run.py` 无对应命令**：

| 路径 | 说明 |
|------|------|
| `feeds/collect.py` | 全自选文字素材批量采集（`collect_all_feeds`）；`FeedItem` 被 news query 引用 |
| `quote/snapshot/cache.py` | `write_snapshot_cache()` → `data/snapshot_{date}.json`；`structure_from_stocks()` 被 quote query 使用 |
| `core/config.py` | `health_cfg()` / `probe_cfg()` 预留，当前无 health CLI |
| `market/sentiment.py` | `collect_open_market_context()` 预留，当前无 CLI |

---

## 快速验收命令清单

```bash
python run.py ecosystem collect --force --date 2026-06-09
python run.py market collect --force --date 2026-06-09
python run.py cls collect --articles --force --date 2026-06-09
python run.py quote query --codes 600519,000001
python run.py quote query --all
python run.py announcement query --codes 600519 --days 3 --max-count 5
python run.py announcement query --codes 600519,000001
python run.py news query --codes 600519 --days 3
python run.py news query --codes 600519,000001 --strict
python run.py auction --force --codes 600519,000001
python run.py index collect --force --date 2026-06-09
python run.py flow collect --force --date 2026-06-10
python run.py flow collect --force --no-watchlist --date 2026-06-10
python -m unittest discover -s tests -v
```
