# ZXTT 重构技术方案与迭代验证计划

> 记录日期：2026-06-13  
> 目的：为“完全重构该方案”沉淀可执行的技术选型、目标架构、阶段计划与验证门禁。

## 1. 当前结论

ZXTT 当前是一个 Python A 股数据采集与报告生成工具集，核心能力包括：

- 9 个基础采集 / 查询模块：财联社、行情、公告、资讯、竞价、盘中监控、大盘生态、指数、资金流。
- 3 条报告管线：早盘、午间、晚间。
- 本地 Web / Hub / 设置页 / 微信推送。
- 文件系统 JSON 与 HTML 作为主要运行时产物。

现状不是单点问题，而是工程结构、报告管线、测试环境和 legacy 兼容层共同造成的复杂度累积。重构应优先保护既有 CLI、落盘路径、JSON schema 和报告产出，再逐步替换内部实现。

## 2. 技术方案选择

### 2.1 保留 Python，不跨语言重写

推荐继续使用 Python 作为主语言。

原因：

- 现有业务资产集中在 Python：AkShare、httpx 抓取、JSON 落盘、AI prompt、HTML 渲染、unittest。
- A 股数据源、网络抓取、文件归档、计划任务脚本都已围绕 Python 建立。
- 跨语言重写会同时破坏数据采集、报告生成、测试 fixture 与运维脚本，风险高于收益。

### 2.2 目标工程形态

推荐目标：

```text
zxtt/
  cli/                  # argparse 命令注册与参数解析
  core/                 # 配置、路径、交易日历、IO、健康检查
  collectors/           # quote / cls / market / flow / index 等采集器
  pipeline/             # ReportPipeline、SlotConfig、manifest、status
  reports/              # HTML、Hub、归档、推送
  ai/                   # LLM、prompt、合成与解析
tests/
docs/
run.py                  # 兼容薄入口
pyproject.toml
```

关键原则：

- 外部命令不变，内部模块可重组。
- 数据路径不 silent change。
- JSON schema 变更必须有兼容层和契约测试。
- legacy 行为必须显式可开关、可观测、可测试。

### 2.3 工程化选型

| 维度 | 推荐 |
|------|------|
| 包管理 | `pyproject.toml` + editable install |
| 入口 | 保留 `python run.py ...`，新增包入口作为内部目标 |
| 测试 | 先保留 `unittest`，补 fixture 和契约测试；后续再评估 pytest |
| Lint | `ruff check` |
| 格式 | 先不强制大面积格式化，避免无效 diff；新代码遵守 ruff |
| CI | GitHub Actions 跑依赖安装、ruff、unittest |
| 配置 | `config.yaml` + `.env`，legacy 显式化 |

## 3. 必须保护的边界

### 3.1 CLI 契约

以下命令和主要参数应保持兼容：

```bash
python run.py quote query --codes 600519
python run.py quote query --all
python run.py announcement query --codes 600519
python run.py news query --codes 600519
python run.py ecosystem collect
python run.py market collect
python run.py cls collect --articles
python run.py index collect
python run.py flow collect
python run.py auction
python run.py intraday
python run.py evening
python run.py midday
python run.py morning
python run.py collect --slot evening
python run.py preprocess --slot evening
python run.py generate --slot evening
python run.py reproduce --slot evening --phase verify
```

### 3.2 落盘路径

P0 路径不可 silent 变更：

- `data/quote_query_{date}.json`
- `data/announcement_query_*`
- `data/news_query_*`
- `data/market_sentiment/`
- `data/market_index/`
- `data/market_flow/`
- `data/cls_finance/`
- `data/cls_articles/`
- `data/auction_trend_*`
- `data/intraday_series_*`
- `data/intraday_digest_*`
- `data/evening_context/`
- `data/midday_context/`
- `data/scheduled_ai/`
- `data/expectations/`
- `data/report_hub/`
- `reports/{date}/daily_evening.html`
- `reports/{date}/daily_midday.html`
- `reports/{date}/daily_morning.html`

### 3.3 Web 与 Hub 契约

需要保持：

- `GET /api/health`
- `GET /api/settings`
- `POST /api/settings`
- `/reports/*`
- `/data/*`
- `/settings`
- Hub slot：`evening_prev`、`morning`、`midday`、`evening`

## 4. 当前基线验证结果

已执行：

```bash
python3 -m pip install -r requirements.txt
python3 -m unittest discover -s tests -v
python3 run.py calendar verify --year 2026
python3 run.py auction --simulate --date 2026-06-10
python3 run.py intraday --simulate --date 2026-06-10
```

结果：

- `calendar verify` 通过。
- `auction --simulate` 通过。
- 全量单测执行到 `Ran 243 tests`，结果为 `failures=13, errors=20, skipped=3`。
- `intraday --simulate` 失败，原因是模拟流程会打开 Hub，Hub 进一步触发 snapshot 加载自选股，本地缺少 `ths.account_dir`。

主要失败类型：

1. 缺少离线 fixture：`data/quote_query_2026-06-10.json`。
2. 缺少本地同花顺配置：`ths.account_dir` 或 legacy 配置。
3. Hub / snapshot / intraday simulate 与本地自选股配置耦合。
4. Windows 路径断言跨平台失败：`D:/ths/...` 与 `D:\ths\...`。

结论：正式拆业务前，必须先稳定测试基线和环境隔离。

## 5. 分阶段重构计划

### S0：稳定基线

目标：让测试在无本地同花顺、无 Windows 路径、无真实 `config.yaml` 的环境中可复现。

产出：

- 补齐最小离线 fixture：
  - `quote_query_2026-06-10.json`
  - Hub/report 所需最小 HTML/JSON 样本
- 将依赖本地同花顺目录的测试改为 mock 或条件 skip。
- 修复跨平台路径断言。
- 解耦 `intraday --simulate` 与 Hub 打开副作用，或提供测试模式开关。

门禁：

```bash
python3 -m unittest discover -s tests -v
python3 run.py calendar verify --year 2026
python3 run.py auction --simulate --date 2026-06-10
python3 run.py intraday --simulate --date 2026-06-10
```

### S1：标准包化与 CI

目标：让项目成为标准 Python 工程。

产出：

- 新增 `pyproject.toml`。
- 支持 `python3 -m pip install -e .`。
- 移除业务路径对 `sys.path.insert(0, "packages")` 的依赖。
- 添加 ruff 配置。
- 添加 CI：安装依赖、ruff、unittest。
- `run.py` 变成兼容薄入口。

门禁：

```bash
python3 -m pip install -e .
python3 run.py --help
python3 -m unittest discover -s tests -v
ruff check .
```

### S2：抽取 evening / midday 共享采集层

目标：消除午间与晚间的镜像复制。

优先合并：

- collect manifest
- quote 状态检查
- announcement / news 并发查询
- market sentiment / index / flow 状态封装
- feeds digest
- feeds fingerprint
- normalize 基础工具

建议新增：

```text
zxtt/pipeline/
  collect.py
  manifest.py
  feeds_digest.py
  fingerprint.py
  slot_config.py
```

门禁：

```bash
python3 -m unittest tests.test_evening_collect tests.test_midday_collect -v
python3 -m unittest tests.test_evening_preprocess tests.test_midday_preprocess -v
```

### S3：统一三报告管线

目标：用统一 `ReportPipeline` 管理 morning、midday、evening。

建议模型：

```python
ReportPipeline(
    slot="evening",
    collect=...,
    preprocess=...,
    generate=...,
    render=...,
)
```

Slot 差异通过 `SlotConfig` 表达：

- 采集源集合
- prompt key
- HTML renderer
- expectations 写入规则
- 是否需要 cls articles
- 是否依赖 auction / intraday

门禁：

```bash
python3 -m unittest tests.test_morning -v
python3 -m unittest tests.test_evening_generate tests.test_midday_generate -v
python3 -m unittest tests.test_evening_render tests.test_midday_render -v
python3 run.py reproduce --slot evening --phase verify --date 2026-06-10
```

### S4：拆分 CLI

目标：消除 `run.py` God Object。

建议结构：

```text
zxtt/cli/
  main.py
  market.py
  quote.py
  feeds.py
  report.py
  watch.py
  calendar.py
```

兼容要求：

- `python run.py ...` 完全保留。
- 子命令 help 文案保持可读。
- 退出码语义不变。
- 终端输出字段不 silent change。

门禁：

```bash
python3 run.py --help
python3 run.py quote query --codes 600519
python3 run.py collect --slot evening --force --date 2026-06-10
python3 run.py preprocess --slot evening --force --date 2026-06-10
python3 run.py generate --slot evening --phase render --force --date 2026-06-10
```

### S5：清理 schema 双轨与 legacy

目标：减少历史命名和老项目路径耦合。

处理：

- 明确 `pool_*` 为主字段，`emotion_*` 作为兼容字段。
- 保留 `market collect` 作为 `ecosystem collect` alias。
- `legacy.zxreport_config` 改为显式开关：

```yaml
legacy:
  enabled: true
  zxreport_config: D:\ZXReport\config.yaml
```

- 对 legacy merge 来源输出诊断信息。
- `industry_cache` 从隐式读取老项目文件，迁移为可配置缓存。

门禁：

```bash
python3 -m unittest tests.test_settings tests.test_quote_query tests.test_quote_query_cache -v
python3 run.py settings --help
```

### S6：补齐或移除未完成入口

当前 `eve-news` 已注册 CLI，但实现文件标注“管线待实现”。

需要二选一：

1. 实现完整 `eve-news` 管线。
2. 从正式 CLI 中隐藏或标记 experimental，避免用户误用。

门禁：

```bash
python3 run.py --help
python3 run.py eve-news --help
```

## 6. 每轮迭代的验证策略

每一轮改动遵循：

1. 先跑相关模块测试。
2. 再跑全量 unittest。
3. 如果触及 CLI，跑 CLI smoke。
4. 如果触及报告产物，跑 reproduce 或 golden diff。
5. 如果触及配置，跑 settings / legacy / 无 config 环境测试。

推荐基础门禁：

```bash
python3 -m unittest discover -s tests -v
python3 run.py calendar verify --year 2026
python3 run.py auction --simulate --date 2026-06-10
python3 run.py intraday --simulate --date 2026-06-10
```

报告相关门禁：

```bash
python3 run.py collect --slot evening --force --date 2026-06-10
python3 run.py preprocess --slot evening --force --date 2026-06-10
python3 run.py generate --slot evening --phase render --force --date 2026-06-10
python3 run.py reproduce --slot evening --phase verify --date 2026-06-10
```

## 7. 推荐优先级

优先级从高到低：

1. **S0 稳定基线**：没有可复现测试，不应开始大规模业务拆分。
2. **S1 包化与 CI**：让每次重构都有自动门禁。
3. **S2 合并 evening / midday 重复代码**：这是当前最高收益的结构性改动。
4. **S3 统一报告管线**：在共享层稳定后再抽象三 slot。
5. **S4 拆 CLI**：先保持行为，再替换内部注册机制。
6. **S5/S6 清理 legacy 和未完成入口**：降低长期维护成本。

## 8. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 数据源网络不稳定 | 单测使用离线 fixture，联网命令只做 smoke |
| 本地同花顺路径不可用 | watchlist 层提供 mock / fallback / 条件 skip |
| JSON schema 被误改 | 增加 golden sample 与契约测试 |
| CLI 行为被破坏 | 保留 run.py 兼容入口并添加 CLI smoke |
| 大面积移动文件导致 import 断裂 | 先包化，再逐模块迁移，保留 compatibility wrapper |
| legacy 兼容不透明 | 显式 `legacy.enabled`，记录 merge 来源 |

## 9. 下一步建议

下一步应从 S0 开始：

1. 补齐 `quote_query_2026-06-10.json` 离线 fixture。
2. 让 Hub / snapshot / intraday simulate 在无同花顺配置时可测试。
3. 修复跨平台路径断言。
4. 让 `python3 -m unittest discover -s tests -v` 作为真正基线通过。

完成 S0 后，再进入包化和共享管线抽取。
