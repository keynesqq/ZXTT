# ZXReport → ZXTT 晚间管线对照表

> 开发总览：[`evening-dev.md`](evening-dev.md) · 只读源：`D:\ZXReport`  
> 更新：2026-06-10

## 一句话

迁代码时按本表定位老项目文件对应的 **ZXTT 步骤 / 包路径**；行为以 ZXTT 定稿为准，老项目仅作参考。

---

## 一、流水线对照

| 能力 | ZXReport（老） | ZXTT（新） |
|------|----------------|------------|
| 总编排 | `report_pipeline.py` / `ai_evening_pipeline.py` | `packages/evening/collect.py` · `preprocess` · `generate`（待实现） |
| 盘后 slot | `schedule.slots.evening` | `run.py generate --slot evening` |
| 上下文包 | 现场拼 prompt | `data/evening_context/{date}.json` |
| 采集健康 | `collect_health.py` | ② `collect_manifest` + ③ 3.2 `health` |

---

## 二、分步对照

### 第 1 步 · 自选

| 老项目 | ZXTT |
|--------|------|
| `ths_blocks.py` / `watchlist.py` | `packages/watchlist/` |
| `settings.py` analyze_blocks | `config.ths.analyze_blocks` |
| 快照 cache | `packages/quote/query_cache.py` → `quote_query_{date}.json` |

### 第 2 步 · 采集

| 老项目 | ZXTT |
|--------|------|
| `collect_health.py` 各源检查 | `docs/evening-step2-collect.md` manifest |
| `market_sentiment.py` | `packages/market/ecosystem/` · `ecosystem collect` |
| `cls_request.py` / 财联社 | `packages/market/cls/` · `cls collect` |
| feeds 批量 collect | **不迁**；改用 `announcement query` + `news query` |
| 指数/flow | `packages/market/index/` · `flow/` |

### 第 3 步 · 预处理

| 子步 | 老项目 | ZXTT |
|------|--------|------|
| 3.1 合并 | `prompt_builders.py` 现场读多文件 | `packages/evening/normalize.py` `build_evening_bundle` |
| 3.2 健康 | `collect_health.py` | `packages/evening/health.py` |
| 3.3 事件 | `events.py` | `packages/events/`（label 改中文六档） |
| 3.4 标签 | `report_prompts.py` snapshot 行 | `packages/evening/tags.py` |
| 3.5 大盘 | `market_sentiment.format_*` | `packages/evening/market_local.py`（**无** L1/L2 AI digest） |
| 3.6 feeds digest | `ai_digest_stocks.py` | `packages/evening/feeds_digest.py` |
| 3.7 拼包 | `prompt_builders.py` / `report_prompts.py` | `packages/evening/assemble.py` |
| 3.8 cls digest | `ai_digest_cls.py` | `packages/evening/cls_digest.py` |
| 指纹缓存 | `ai_digest.py` | `packages/evening/feeds_fingerprint.py` |
| 解析 digest JSON | `ai_digest_parse.py` | `packages/ai/parse.py`（或 evening 子模块） |

**不迁**：`ai_digest_market.py`（L1 AI）、`ai_digest_market` + theme L2 AI（ZXTT 3.5 本地）。

### 第 4 步 · AI

| 老项目 | ZXTT |
|--------|------|
| `llm.py` `EVENING_SYSTEM` | `packages/ai/prompts.py`（见 `evening-prompts.md` 补丁） |
| `scheduled_ai.py` save + **内嵌推送** | `packages/evening/generate.py`（**不推送**） |
| `expectation_parse.py` | `packages/evening/expectations.py` |
| `ai_verify.py` | `packages/evening/verify.py`（事实库缩小） |
| `AI_RULES.md` | 补丁覆盖：31 只同级、【观察】、中文 label |

### 第 5 步 · 触达

| 老项目 | ZXTT |
|--------|------|
| `report_render.py` | `packages/report/render.py` |
| `push_summary_format.py` | `packages/report/push.py`（+【观察】+ label） |
| `wechat_push.py` | 同上，**仅 5C** 调用 |
| `templates/daily_report.html` | `templates/daily_evening.html`（三 Tab MVP） |
| `templates/partials/snapshot_*` | `evening_snapshot_panel` |
| `templates/partials/feeds_grouped_*` | 审计模式可选 |
| `templates/partials/digest_appendix.html` | 去掉 market_l1/l2 段 |

---

## 三、数据路径对照

| 用途 | ZXReport | ZXTT |
|------|----------|------|
| 行情 | `snapshot_{date}.json` 等 | `quote_query_{date}.json` |
| 公告资讯 | `feeds_cache/` | `announcement_query_*` + `news_query_*` |
| AI 原文 | `scheduled_ai/` 多记录 | `scheduled_ai/evening_{date}.json` |
| 预期 | `expectations/` | 同，键改为 `stocks[code]` |
| digest | `ai_digest/` | 同路径思路 `data/ai_digest/{date}/` |
| 报告 HTML | `reports/` | `reports/{date}/daily_evening.html` |

---

## 四、配置对照

| 键 | ZXReport | ZXTT |
|----|----------|------|
| 板块白名单 | `ths.analyze_blocks` | 同 + `evening-config.md` |
| LLM | `llm.*` | legacy 继承 + 本地覆盖 |
| 事件词表 | `events:` | `events:` + 3.3 默认表 |
| 微信 | 隐式在 save | `wechat.enabled` 仅第 5 步 |
| 晚间专用 | 分散 | `evening.*` 集中 |

---

## 五、迁代码检查清单

- [ ] 事件 label 已改为中文六档，非 ⛔/★  
- [ ] 推送摘要含【观察】  
- [ ] 第 4 步不调用 `wechat_push`  
- [ ] 合成不拼 7 路 raw，只读 `evening_context.prompt`  
- [ ] 快照 35 行来自 `join_quotes_with_memberships`  
- [ ] cls digest 全文不截断 1200  
- [ ] 无 market_l1/l2 AI digest 依赖  

---

## 六、定稿勾选

- [x] 五步 × 老文件映射  
- [x] 明确不迁项（feeds collect、market AI digest）  
- [x] 路径与配置对照  

**对照表已定稿。**
