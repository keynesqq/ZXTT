# 大盘资金流模块方案（P1 · 修订版）

> 模块代号：`flow` · 命令：`python run.py flow collect`  
> 状态：**v1 已打包验收**（2026-06-10）  
> 更新：2026-06-10（L4 ulist 批量；L2 push2his 合并口径；共享 httpx 会话）

## 1. 定位

| 口径 | 名称 |
|------|------|
| **产品名** | 大盘资金流 |
| **命令 slug** | `flow` |
| **命令** | `python run.py flow collect` |
| **不是** | 财联社长文、最终大盘情绪、龙虎榜席位、个股行情 |

**一句话：** 东财结构化拉 **北向 + 大盘主力 + 行业 TOP +（可选）自选主力**，独立落盘，供与 cls / 生态 / 指数印证。

---

## 2. 做什么

| 层级 | 内容 | MVP |
|------|------|-----|
| **L1 北向** | 沪股通/深股通成交净买额、通道状态 | ✅ |
| **L2 大盘** | 沪深两市主力/超大单/大单/中单/小单净流入 | ✅ |
| **L3 板块** | 行业流入/流出 TOP N | ✅（仅**当日**） |
| **L4 自选** | 配置板块内各股当日主力净流入 | ✅ **默认开，可关** |
| **L5 概念/地域** | 概念板块资金流 | v3 |

### 2.1 自选（L4）开关

| 入口 | 行为 |
|------|------|
| `config.yaml` → `flow.watchlist_enabled` | 默认 **`true`**（拉自选） |
| `python run.py flow collect --no-watchlist` | 单次跳过 L4 |
| `python run.py flow collect --watchlist` | 单次强制拉（覆盖 config 关） |

**不做：** 全 A 股扫描；龙虎榜；从 cls 长文 NLP 抽资金。

### 2.2 L4 实现（稳定版）

1. **主路径**：东财 `push2/ulist.np/get` 批量 `secids`（31 只通常 **1 次**请求）。  
2. **兜底**：全市场排行分页 → AkShare `stock_individual_fund_flow_rank`。  
3. 与 `watchlist.load_stocks()` code 集合对齐，落盘 `watchlist_flow[]`。  
4. 缺数据 → `main_net_yi: null` + 可选 warning。

---

## 3. `--date` 与数据源（审查修订 · 必遵）

| 层级 | 当日采集 | 历史 `--date` |
|------|----------|---------------|
| L1 | `stock_hsgt_fund_flow_summary_em` | `stock_hsgt_hist_em("北向资金")` + 沪/深股通 hist 分行 |
| L2 | push2his 当日合并行 | 同左 |
| L3 | `stock_sector_fund_flow_rank` | **skip**，`warnings` 说明「板块榜仅支持当日」 |
| L4 | rank 交集 | **skip**（与 L3 同因）；或 v3 用 hist 逐股 |

**北向主字段：** **成交净买额**（亿元）；`资金净流入` 可写入 `northbound.extra.net_inflow_yi` 备查。

**单位：** hsgt summary/hist 已为亿元；market / sector / rank 净额 **元 → `/1e8` 亿元**，在 `flow_sources.py` 集中换算。

---

## 4. 怎么做

### 4.1 代码

```
run.py flow collect
  → packages/market/flow_snapshot.py   # 编排、slot 合并、flow_score、落盘
  → packages/market/flow_sources.py    # 直连优先 + AkShare 兜底 + 归一
  → packages/market/flow_eastmoney.py  # httpx 直连、节流、ulist/push2his
  → feeds/eastmoney.call_akshare       # 兜底
  → watchlist.loader.load_stocks       # L4
  → collect/manifest.track_source
```

manifest 源：`akshare_hsgt`、`akshare_market_flow`、`akshare_sector_flow`、`akshare_watchlist_flow`（L4 关闭时 skip）。

### 4.2 采集顺序

1. 交易日检查；`flow.enabled` 关则 skip。  
2. 开共享 httpx 会话；**串行** L1 → L2（避免东财并发断连）；L3、L4 串行。  
3. L2 盘中读 push2his **当日行**；无当日行则兜底最近一日 + warning（**不用**上证+深证 ulist 相加）。  
4. L4 仅当 `watchlist_enabled` 且非历史 skip。  
5. `_score_flow` → `flow_score` / `flow_signal` / `flow_hint`。  
6. `--slot` 合并 `snapshots[]`；写 `data/market_flow/{trade_date}.json`。

### 4.3 命令

```bash
# 默认：北向 + 大盘 + 行业 TOP + 自选
python run.py flow collect --force --date 2026-06-10

# 不要自选（快一点）
python run.py flow collect --force --no-watchlist

# 午间快照
python run.py flow collect --force --slot midday --date 2026-06-10
```

### 4.4 配置（`config.example.yaml`）

```yaml
flow:
  enabled: true
  primary: eastmoney_direct      # 默认东财 httpx 直连
  fallback: eastmoney_akshare    # 直连失败时 AkShare 兜底
  watchlist_enabled: true
  sector_top_n: 10
  sector_max_pages: 3
  stock_rank_max_pages: 80
  request_interval_sec: 1.0
  stock_batch_size: 50
  watchlist_missing_warn: true
```

新增 `core.config.flow_cfg()`；超时复用 `feeds.akshare_timeout_sec`。

### 4.5 `flow_signal`（v1 规则）

| 输入 | 分档 |
|------|------|
| 北向成交净买额 | ≥30 亿强 / ≤-30 亿弱 / 否则中 |
| 大盘主力净流入 | 同左（亿元） |

合成：两强→强；两弱→弱；其余→中。`flow_hint` 一句中文，禁止引用涨停家数或 cls。

---

## 5. 输出什么

**路径：** `data/market_flow/{trade_date}.json`

| 字段组 | 代表字段 |
|--------|----------|
| 元数据 | `schema_version`、`trade_date`、`calendar_date`、`latest_slot`、`collected_at_iso` |
| 北向 | `northbound.net_yi`、`sh_connect_net_yi`、`sz_connect_net_yi`、`connect_status` |
| 大盘 | `market.main_net_yi`、`super_large_net_yi`、`large_net_yi`… |
| 板块 | `sectors_inflow_top[]`、`sectors_outflow_top[]` |
| 自选 | `watchlist_flow[]`、`watchlist_enabled`（本次是否采） |
| 参考分 | `flow_score`、`flow_signal`、`flow_hint` |
| 多时段 | `snapshots[]` |
| 告警 | `warnings[]` |

**终端：** `outcome`、`north_net_yi`、`main_net_yi`、`watchlist_count`、`flow_signal`、`path`。

**下游：** `format_flow_prompt(load_market_flow(trade_date))`。

---

## 6. 分期

| 期 | 内容 |
|----|------|
| **v1** | L1–L4（自选可关，**默认开**）+ CLI + JSON + manifest + 单测 mock |
| **v2** | `collect evening` / `collect health` / probe 一项 |
| **v3** | 概念板块、历史板块、与生态行业 fuzzy 印证 |

v1 **不**接入 evening 编排。

---

## 7. 验收标准（v1）

- [x] `flow collect --force` → `outcome: ok`；默认 `watchlist_count` = 自选不重复只数（31）  
- [x] `--no-watchlist` → `watchlist_flow: []`，`watchlist_enabled: false`  
- [x] 当日：北向、大盘、行业 TOP、自选主力均有值（允许个别股 null；本次 31/31）  
- [x] 历史 `--date`：北向+大盘有值；板块+自选 skip + warnings  
- [x] JSON 不写入 `market_sentiment` / `cls_finance`  
- [x] manifest 四源（L4 关时为 skip）  
- [x] 单测 mock **14** 条（含 watchlist 开/关、大盘 push2his 路径）

---

## 8. 风险

| 风险 | 对策 |
|------|------|
| L3/L4 rank 全分页慢 | 接受或超时降级；L4 关 `--no-watchlist` 减负 |
| 东财限流 | 共享 httpx 会话 + `request_interval_sec` 节流；L1/L2 串行 |
| 行业名 ≠ 生态 `hot_industries` | v1 只并存，解读层对照 |
| 历史日无板块/自选 | 文档 + warnings，非 fail |

---

*关联：[`packaged-modules.md`](packaged-modules.md) §8*
