# 22 点晚间报告 · 运维 Runbook

> 开发总览：[`evening-dev.md`](evening-dev.md) · 五步详文：step1–5 · 配置：[`evening-config.md`](evening-config.md)  
> 更新：2026-06-10

## 一句话

交易日 **22:00** 按本清单跑通「采集 → 预处理 → AI → 渲染」；部分步骤可降级，**quote 失败则中止**。

---

## 一、时间线（建议）

| 时刻 | 动作 | 步 |
|------|------|-----|
| 15:00 后 | 可选：手动跑大盘三件套（生态/指数/flow） | ② 部分 |
| 17:00–18:00 | `quote --all` + 公告 + 资讯 | ①② |
| 20:00 后 | `cls collect --articles`（`data_watch` 常此时出） | ② |
| **22:00** | 全链：重采 cls → preprocess → generate | ②③④⑤ |

非交易日：各 `collect` 加 `--force --date YYYY-MM-DD`。

---

## 二、22:00 标准命令序列（规划态）

> `collect` / `preprocess` / `generate` **待实现**；当前用等价手动命令。

```bash
# === ② 采集（若无当日数据）===
python run.py quote query --all
# … 见 evening-step2-collect.md 手动 7 步 …

# === ③ 预处理前：重采财联社 B 层（必须）===
python run.py cls collect --articles

# === ③ 本地预处理 3.1–3.8 ===
python run.py preprocess --slot evening

# === ④ AI ===
python run.py generate --slot evening --phase ai

# === ⑤ HTML + 微信 ===
python run.py generate --slot evening --phase render

# 或一次跑完 ④⑤：
python run.py generate --slot evening
```

`evening.preprocess_cls_recollect=true` 时，编排应在 `preprocess` 内自动执行 `cls collect --articles`。

---

## 三、每步前置检查

| 步 | 检查项 | 不满足时 |
|----|--------|----------|
| ① | `config.yaml` 有 `ths.account_dir` + `analyze_blocks` | 配置同花顺 |
| ② | `quote_query_{date}.json` 存在，`code_count≥1` | 先 `quote --all` |
| ② | `collect_manifest`（实现后）`overall≠fail` | 补采失败模块 |
| ③ | 7 路 raw 路径齐（见 step2 表） | 回 ② |
| ③ | `cls_articles` 尽量 5/5；4/5 可继续 | ③ 标 `complete=false` |
| ④ | `evening_context/{date}.json` 存在；`prompt.stocks` 数 = `code_count` | 回 ③ |
| ⑤ | `scheduled_ai/evening_{date}.json` 存在（无则降级页） | 先 ④ 或接受降级 |
| ⑤ | `wechat.enabled` 时才推送 | 仅 HTML |

**快速目检（2026-06-10 基线）**：`code_count=31`，`row_count=35`，`cls 4/5` 可出报告。

---

## 四、失败降级（仍出报告）

| 情况 | 行为 |
|------|------|
| flow 大盘主力失败 | ③ `trust_flags.market_main_flow=false`；④ 禁编造主力 |
| cls 4/5 缺 `data_watch` | ③ `cls_digest.complete=false`；④ 读 `missing_note` |
| 部分 feeds digest 失败 | ③ `on_digest_fail=degrade`；该股标 failed |
| LLM 合成失败 | ④ 不写 `expectations`；⑤ 降级页 |
| 微信推送失败 | ⑤ 记 `push_error`；HTML 仍落盘 |
| AI 漏股 | ④ `missing_codes` + warn |

---

## 五、重跑规则

| 场景 | 建议 |
|------|------|
| 仅改自选板块 | 重跑 ① `quote --all` → ② → ③ |
| 仅行情变了 | ② quote → ③（feeds 指纹不变可 reuse digest） |
| 仅新增公告资讯 | ③ 自动 refresh 变码的 feeds digest |
| 补采 cls 第 5 篇 | `cls collect --articles` → **只重跑 ③**（不必重 ② 全盘） |
| 不满意 AI 文案 | 只重跑 `generate --phase ai` → `render` |
| 同日第二次 preprocess | 覆盖 `evening_context`、`evening_baseline`（3.6 双基准防漏 refresh） |

**不要**：第 4 步重跑 3.6/3.8 digest（除非先重跑 ③）。

---

## 六、产出核对清单

| 文件 | 存在 | 关键字段 |
|------|------|----------|
| `data/evening_context/{date}.json` | ③ 后 | `meta.context_as_of`、`prompt.stocks`×31 |
| `data/ai_digest/{date}/manifest.json` | ③ 后 | `stages.feeds_digests`、`stages.cls_digests` |
| `data/scheduled_ai/evening_{date}.json` | ④ 后 | `body`、`summary` |
| `data/expectations/{下一交易日}.json` | ④ 后 | `stocks[code]` |
| `reports/{date}/daily_evening.html` | ⑤ 后 | 可浏览器打开 |
| `data/last_report.json` | ⑤ 后 | `path` 指向 HTML |

样例结构：[`evening-schemas.md`](evening-schemas.md)。

---

## 七、验收（PM / Agent 代跑）

1. 打开 `reports/{date}/daily_evening.html` — 三 Tab、35 行快照  
2. 顶栏：31/35、cls 4/5（或 health 摘要）  
3. 点击代码跳转 `#stock-{code}`  
4. 微信（若开启）：摘要含【观察】  
5. `expectations` 下一交易日文件存在  

---

## 八、定稿勾选

- [x] 22:00 命令序列  
- [x] preprocess 前 cls 重采  
- [x] 前置检查与降级  
- [x] 重跑边界  

**Runbook 已定稿。**
