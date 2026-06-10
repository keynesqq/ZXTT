# 22 点晚间报告 · JSON 契约与样例

> 开发总览：[`evening-dev.md`](evening-dev.md) §四 · 样例：[`samples/`](samples/)（2026-06-10）  
> 字段细节：step3 / step4 / step5 详文 · 更新：2026-06-10

## 一句话

晚间链路在 `data/` 与 `reports/` 之间传递 **6 类主 JSON**；本文列顶层键，完整样例见 `docs/samples/`。

---

## 一、文件索引

| 文件 | 写入步 | 读取步 | 样例 |
|------|--------|--------|------|
| `data/collect_manifest/{date}.json` | ② | ③ 3.2 | （见 step2 §五；实现后补样例） |
| `data/evening_context/{date}.json` | ③ 3.8 | ④⑤ | [`evening_context_2026-06-10.json`](samples/evening_context_2026-06-10.json) |
| `data/evening_baseline/{date}.json` | ③ 3.6 | ③ 次日 3.6 | [`evening_baseline_2026-06-10.json`](samples/evening_baseline_2026-06-10.json) |
| `data/ai_digest/{date}/manifest.json` | ③ 3.6+3.8、④ | ④④D、⑤ 可选 | [`ai_digest_manifest_2026-06-10.json`](samples/ai_digest_manifest_2026-06-10.json) |
| `data/scheduled_ai/evening_{date}.json` | ④ | ⑤ | [`scheduled_ai_evening_2026-06-10.json`](samples/scheduled_ai_evening_2026-06-10.json) |
| `data/expectations/{target_date}.json` | ④ | ⑤ 脚注、盘前 | [`expectations_2026-06-11.json`](samples/expectations_2026-06-11.json) |

**② 原始输入**（已有真实数据）：`quote_query_*`、`announcement_query_*`、`news_query_*`、`market_*`、`cls_*` — 结构见 [`packaged-modules.md`](packaged-modules.md)。

---

## 二、`evening_context`（slim）

第 4 步**主读** `prompt`；不含 `feeds_merged` 全文。

| 顶层键 | 必填 | 说明 |
|--------|------|------|
| `schema_version` | ✅ | 固定 `1` |
| `meta` | ✅ | `trade_date`、`context_as_of`（3.8 写）、`code_count`、`row_count`、`cls_articles_found`、`paths` |
| `group_order` | ✅ | 板块 Tab 顺序 |
| `memberships` | ✅ | 35 行归属 |
| `structure` | ✅ | `groups[]` 索引 |
| `health` | ✅ | `global`、`health_brief`、`trust_flags` |
| `market_local` | ✅ | `l1_brief`、`l2_brief`、`constraints` |
| `events_by_code` | ✅ | 31 code 事件索引 |
| `industry_in_hot_by_code` | ✅ | code → bool |
| `by_code` | ✅ | 每股 `local_block` + `feeds_digest_ref` |
| `feeds_digest_by_code` | ✅ | ③ 3.6 索引 |
| `prompt` | ✅ | `priority_instructions`、`global`、`feeds_digest_bundle`、`events_block`、`cls`、`stocks[]` |
| `cls_digest` | ✅ | 五栏汇总、`complete` |
| `cls_mentions_by_code` | 可选 | 财联社点名自选 |

---

## 三、`evening_baseline`

③ 3.6 指纹基准；**仅公告+资讯**条目参与 fingerprint。

| 顶层键 | 说明 |
|--------|------|
| `trade_date` | 当日 |
| `prev_trade_date` | 上一交易日 |
| `codes[code].fingerprint` | 哈希 |
| `codes[code].item_counts` | 五类条数 |
| `codes[code].last_digest_trade_date` | 上次成功 digest 日 |
| `codes[code].last_digest_source_id` | 如 `stock_600021` |

---

## 四、`ai_digest/manifest.json`

单文件合并 **feeds digest + cls digest + synthesize** 元数据。

| 顶层键 | 说明 |
|--------|------|
| `schema_version` | `1` |
| `trade_date` | 日历日 |
| `stages.feeds_digests` | 3.6 批处理结果 |
| `stages.cls_digests` | 3.8 五栏结果 |
| `stages.synthesize` | ④ 单次 LLM |
| `entries[]` | `{kind, source_id, path}` |

单篇 feeds：`data/ai_digest/{date}/stock_{code}.json`  
单篇 cls：`data/ai_digest/{date}/cls_{slot_key}.json`

---

## 五、`scheduled_ai/evening_{date}.json`

| 键 | 说明 |
|----|------|
| `summary` | 微信/顶栏摘要（含【观察】等） |
| `body` | Markdown 正文，`### code` 分股 |
| `raw` | LLM 原文 |
| `model` | 模型名 |
| `missing_codes` | 漏股列表 |
| `truncated_suspected` | 是否疑似截断 |
| `ai_error` | 失败信息 |

第 5 步**只读**，不重存。

---

## 六、`expectations/{target_trade_date}.json`

| 键 | 说明 |
|----|------|
| `source_trade_date` | 报告日（如 2026-06-10） |
| `target_trade_date` | **下一交易日**（文件名与此一致） |
| `stocks[code]` | 每股短线预期；键为 code 非 group |
| `meta` | 来自 `market_local`，非老项目 `emotion_label` |
| `missing_codes` | 解析失败 code |

---

## 七、样例使用说明

1. 样例为 **结构参考**；`prompt`/`body` 内文用 `…` 占位。  
2. 真实 raw 输入以 `data/` 下 2026-06-10 文件为准。  
3. 实现 ③ 后，用当日产出 **覆盖** `samples/evening_context_*.json` 做回归对照。

---

## 八、验收

- [ ] 打开 5 个样例 JSON，可被 step3/4/5 文档顶层键逐条对上  
- [ ] `evening_context` 样例含 `prompt.cls`、`cls_digest.complete=false`  
- [ ] `expectations` 样例文件名为 **下一交易日**  
