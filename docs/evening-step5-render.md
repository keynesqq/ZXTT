# 第 5 步 · 触达（对齐第 3/4 步 · 定稿）

> 步骤：**⑤ / 5** · 开发总览：[`evening-dev.md`](evening-dev.md)  
> 位置：第 4 步 `scheduled_ai` + `evening_context` → **第 5 步** → HTML + 微信  
> 状态：**规格定稿**；`generate --phase render` **待实现**  
> 前置：[`evening-step3-preprocess.md`](evening-step3-preprocess.md)、[`evening-step4-ai.md`](evening-step4-ai.md)  
> 线框：[`evening-templates.md`](evening-templates.md) · 对照：`D:\ZXReport\src\report_render.py`  
> 更新：2026-06-10

## 一句话

**不调 LLM**；把第 4 步 AI 结论 + 第 3 步事实 **按板块排版给人看**（35 行 Tab），微信推 `summary`；分析正文仍按 **code**（31 只一份）。

---

## 一、与第 3/4 步接口契约

| 来源 | 第 5 步用法 |
|------|-------------|
| `evening_context/{date}.json` | group_order、memberships、health、events_by_code、market_local、by_code.local_block |
| `scheduled_ai/evening_{date}.json` | `body`、`summary`、`ai_error`、`missing_codes`、`truncated_suspected`（**第 4 步已落盘，第 5 步只读**） |
| `quote_query_{date}.json` | `join_quotes_with_memberships` → 35 行快照 |
| `expectations/{下一交易日}.json` | 脚注「明日预期已写入」+ 路径（不重复解析） |
| `ai_digest/{date}/verify.json` | 顶栏校验（可选） |
| `evening_bundle_full.json` | **可选**；素材 Tab 全量 feeds |

| 不做 | 说明 |
|------|------|
| 重调 LLM | 研判正文来自第 4 步 |
| 重存 `scheduled_ai` | 第 4 步已写；第 5 步不重复 save |
| 推送嵌在 save 里 | 老项目如此；ZXTT **仅 5C 推送** |

---

## 二、职责（5A–5D）

| 阶段 | 做 | 不做 |
|------|-----|------|
| **5A** | 组装 `render_ctx` | 拼 AI prompt |
| **5B** | Jinja → HTML | 改 `evening_context` |
| **5C** | 微信推 `summary`（可选） | 在 5A/5B 里推送 |
| **5D** | `last_report.json` | 历史研判列表（MVP 单次） |

```text
evening_context + scheduled_ai/evening_{date}.json
    → 5A render_ctx
    → 5B daily_evening.html + index.html
    → 5C wechat（config 开启时）
    → 5D last_report.json
```

---

## 三、5A · 渲染上下文

### 3.1 顶栏

```text
trade_date, context_as_of, generated_at
subtitle: 「31 只分析 · 35 行板块」  # meta.code_count / row_count
health_brief, trust_flags 人话摘要
cls_articles_found（如 4/5）, cls_digest.complete
missing_codes, truncated_suspected, critical_missing（第 4 步）
verify.overall（可选）
expectations_path → data/expectations/{target}.json
```

### 3.2 研判区

| 字段 | 来源 |
|------|------|
| `ai_summary_html` | `markdown(summary)`；解析器支持【观察】+ 3.3 label |
| `ai_body_html` | `markdown(body)`；每个 `### {code}` 加 `id="stock-{code}"` |
| `ai_error` | 失败时展示；无 AI 时降级文案 |
| `ai_model` | 可选展示 |

**正文导航**：按第 4 步四档 stance 章（我的/想买的/观察/其它）；非按 35 行 group。

### 3.3 重大事件区

- 数据源：`events_by_code`（**按 code 去重**，31 份）
- 展示：大利空/大利好等 **3.3 label** + 待核实 badge
- 附 `groups[]` 标注所属板块
- **不按 membership 展开**，避免同 code 重复

### 3.4 快照区

```text
snapshot_groups ← evening_context.group_order（非 feeds 键序）
snapshot_rows[] ← join_quotes_with_memberships(quotes, memberships)
每行附加：local_block.tags, events_label, stance_label, primary_stance
代码列链接 → #stock-{code}
```

同股多板块：多行共用同一锚点；组内可加「主分析见 {stance_label} 章」。

### 3.5 素材区（默认 slim，对齐 3.7）

无 `evening_bundle_full` 时，按 code 展示：

```text
feeds_digest: status, summary, facts_top, context_note（reuse）
events_display ≤3
```

有 audit 时：全量公告/资讯按 group Tab（迁 `feeds_grouped_panel`）。

### 3.6 大盘摘要条（可折叠）

`market_local.l1_brief`、`l2_brief`、`constraints[]`（3.5 多轴，非单一情绪档）。

### 3.7 Digest 附录（对齐 3.6/3.8）

```text
digest_appendix.sections ←
  cls_digest.items[]（五栏 status/summary）
  + manifest feeds 汇总（refresh/reuse/failed 计数）
```

**不含** market_l1/l2 AI narrative（ZXTT 无）。

---

## 四、5B · HTML（MVP 三 Tab）

| Tab | 内容 |
|-----|------|
| **研判** | 顶栏 + 摘要盒 + AI 正文 + 重大事件 + digest 附录 |
| **行情** | `snapshot_grouped_table`；35 行按 group_order |
| **素材** | slim digest/事件；或 audit 全量 |

**产出**：

```text
reports/{calendar_date}/daily_evening.html
reports/{calendar_date}/index.html
data/last_report.json
```

**MVP 不做**：设置页、盘中刷新、竞价、live 页、scheduled_ai 历史折叠列表。

### 无 AI 降级

有 `evening_context`、无 `scheduled_ai` 时：

- 仍渲染行情 + 健康 + 素材
- 研判区：「AI 未生成，请 `generate --phase ai`」
- 不推微信

---

## 五、5C · 微信推送

| 项 | 约定 |
|----|------|
| 时机 | **仅第 5 步**（第 4 步 save 不推送） |
| 文案 | `scheduled_ai.summary`；无则 `body` 前 280 字 |
| 解析 | 迁 `push_summary_format`；补 **【观察】**；股行支持 **大利空…轻多·** |
| 开关 | `config.wechat.enabled` |
| 失败 | `scheduled_ai.push_error`；不阻断 HTML |

标题示例：`ZXTT 盘后 · {trade_date}`。

---

## 六、5D · manifest

`data/last_report.json`：

```json
{
  "path": "reports/2026-06-10/daily_evening.html",
  "slot": "evening",
  "generated_at_iso": "…",
  "context_as_of": "…",
  "ai_ok": true,
  "push_ok": true
}
```

---

## 七、与老项目差异

| 项 | ZXReport | ZXTT |
|----|----------|------|
| 快照 | 35 行 SnapshotRow | join quote + memberships |
| 事件卡 | cards 按 group | events_by_code 去重 + 行内 events_display |
| scheduled_ai | 多文件 + 历史 | `evening_{date}.json` 单文件 |
| 推送 | 在 save_scheduled_ai | **仅 5C** |
| 摘要段 | 无【观察】 | 须解析【观察】+ label |
| SPA | 四 Tab + 设置 | MVP 三 Tab |

---

## 八、CLI

```bash
python run.py generate --slot evening --phase render
python run.py generate --slot evening    # ai → render
```

**前置**：`preprocess` 产出 `evening_context`；`--phase render` 单独跑时建议已有 `scheduled_ai`（否则降级页）。

---

## 九、实现落点

| 模块 | 职责 |
|------|------|
| `packages/report/render.py` | `build_evening_render_context` |
| `packages/report/push.py` | 微信 + `format_summary_display_html`（含【观察】/label） |
| `packages/evening/render.py` | `run_evening_render` 编排 5A–5D |
| `templates/daily_evening.html` | 晚间 MVP |
| `templates/partials/*` | 对照迁 ZXReport |

页面线框：[`evening-templates.md`](evening-templates.md)。

---

## 十、验收（2026-06-10）

1. `daily_evening.html` 可打开；研判区有摘要+正文（有 AI 时）  
2. 行情 Tab **35 行**；板块顺序与 config 一致  
3. 顶栏：cls 4/5、flow 降级（若 health 有）、31/35 字样  
4. 快照代码可跳到 `#stock-{code}`  
5. 微信含【观察】段（若开启）；第 4 步未跑时不推送  
6. 减持股：重大事件区按 code 一条；行内「利空·待核实」  

---

## 十一、定稿勾选

- [x] 不调 LLM；只读 context + scheduled_ai  
- [x] 35 行 join；31 code 正文；事件按 code 去重  
- [x] 推送仅 5C；scheduled_ai 单文件、不重复 save  
- [x] 【观察】+ 3.3 label 解析器  
- [x] 快照锚点；group_order 驱动 Tab  
- [x] 素材 slim 契约；digest 附录 cls+feeds  
- [x] 顶栏 meta 对齐 3.8/第 4 步  
- [x] 无 AI 降级页  

**第 5 步已定稿。**
