# 第 4 步 · AI 研判（对齐第 3 步 · 定稿）

> 步骤：**④ / 5** · 开发总览：[`evening-dev.md`](evening-dev.md)  
> 位置：3.8 定稿 `evening_context` → **第 4 步** → 第 5 步渲染  
> 状态：**规格定稿**；`generate --phase ai` **待实现**  
> 前置：[`evening-step3-preprocess.md`](evening-step3-preprocess.md) · 后续：[`evening-step5-render.md`](evening-step5-render.md)  
> Prompt：[`evening-prompts.md`](evening-prompts.md) · 对照：`D:\ZXReport\src\llm.py`  
> 更新：2026-06-10

## 一句话

**主读** `evening_context.prompt`（3.7+3.8 已拼好），单次 LLM 合成推送摘要 + 正文，解析 `expectations.json`；不重采、不重跑 digest、不重拼 snapshot。

---

## 一、与第 3 步接口契约

| 第 3 步产出 | 第 4 步用法 |
|-------------|-------------|
| `prompt.priority_instructions` | 原样置顶；**覆盖** AI_RULES「其它可不写」 |
| `prompt.global` | 原样（含 health_brief、constraints、l1/l2_brief + 池子/cls A 详情） |
| `prompt.feeds_digest_bundle` | 每只 status / summary / facts≤5 / context_note |
| `prompt.events_block` | 按 **primary_stance** 四组；标签用 3.3 label |
| `prompt.cls`（3.8） | B 层 digest；遵守 preamble「勿重复 A 层数字」 |
| `prompt.stocks[]` | `{code,name,stance_hint,prompt_line}`，顺序=分析序 |
| `meta.context_as_of`（3.8） | 分析时刻块 |
| `meta.code_count` | 前置校验（31） |
| `cls_mentions_by_code`（3.8） | 可选末段 |
| `by_code.local_block` | **不读**（已压进 prompt） |
| `events_by_code` / `market_local` | **不直读**（已在 prompt 段内） |

**禁止**：`format_snapshot_section`、`build_evening_staged_user_prompt` 式重拼 7 路 raw。

---

## 二、职责（4A–4D）

| 阶段 | 做 | 不做 |
|------|-----|------|
| **4A** | 薄封装 `prompt.*` → user prompt | 重采、重拼 raw |
| **4B** | `EVENING_SYSTEM`（ZXTT 补丁）+ 单次 `chat()` | 重跑 3.6/3.8 digest |
| **4C** | split 摘要、解析预期、漏股校验 | HTML（→第 5 步） |
| **4D** | 可选 verify（feeds+cls+market_local） | market_l1/l2 AI digest |

```text
evening_context/{date}.json
    → 4A user prompt
    → 4B 单次 LLM
    → 4C scheduled_ai + expectations
    → 4D verify（可选）
    → 第 5 步 --phase render
```

---

## 三、4A · User Prompt 组装

顺序与 3.7 §7B **一致**：

```text
build_evening_user_prompt(ctx):

1. format_analysis_time_block(
     context_as_of = meta.context_as_of
   )

2. prompt.priority_instructions

3. prompt.global

4. prompt.feeds_digest_bundle

5. prompt.events_block

6. prompt.cls

7. ## [个股压缩输入]
   for s in prompt.stocks:
     ### {s.code} {s.name} [{s.stance_hint}]
     {s.prompt_line}

8. （可选）## [财联社点名自选]
   cls_mentions_by_code 非空时
```

**超字符预算砍序**（不砍 stocks 条数）：

```text
global「详情」长表 → feeds facts 5→3 → 仍超则 warn
constraints + brief + 31 条 stocks 必选
```

**前置校验**：`len(prompt.stocks) == meta.code_count`；否则 fail。

---

## 四、4B · System Prompt + LLM

### 4.1 来源

Prompt 全文：[`evening-prompts.md`](evening-prompts.md)（`EVENING_SYSTEM` + ZXTT 补丁，覆盖 AI_RULES §3「其它可不写」）。

### 4.2 对齐第 3 步的写作规则

| 来源 | 规则 |
|------|------|
| 3.3 事件 | label：大利空/大利好/利空/利好/轻空/轻多；待核实写全句 |
| 3.3 vs 3.6 | **规则事件优先于** `event_net` |
| 3.4 趋势 | 用 `trend_short`/`trend_mid` 双轴表述，勿自编单一强中弱 |
| 3.4 镜头 | `primary_stance` → 四档分章与动作词（见下） |
| 3.5 L1/L2 | 读 brief + `constraints`；**多轴并列，不裁决单一环境档** |
| 3.2 trust | `constraints` 禁编造大盘/行业主力等 |
| 3.8 cls | `cls_digest.complete=false` 时禁编造缺栏；读 `missing_note` |
| 3.6 reuse | 正文体现 `context_note` |

### 4.3 正文分章（按 primary_stance，非 35 行 group）

| 章 | stance | 动作词 |
|----|--------|--------|
| 我的 · 持仓深度 | holding | 守/减/观望 |
| 想买的 · 候选跟踪 | candidate | 等/试/放弃 |
| 观察 · 跌幅达预期 | watch_right | 观察/等企稳/右侧 |
| 其它 · 风向跟踪 | theme_other | 跟踪（2–4 行/只，**不可省略章**） |

**31 只每只必有 `### {code} {name}`**。

### 4.4 推送摘要（对齐 3.3 label + 3.7 priority）

```text
【环境】← l1_brief + l2_brief 一句（≤40字）
【仓位】← 我的+想买的 总策略（≤35字）

【我的】holding 逐只，不可漏
{label} 代码·名称 | 守/减/观望 | ≤18字

【想买的】candidate 逐只，不可漏
{label} 代码·名称 | 等/试/放弃 | ≤18字

【观察】watch_right 逐只，不可漏
· 代码·名称 | 观察/等企稳/右侧 | ≤18字

【其它】theme_other 有重大 label 者；全无写「无」

【操作】（≤35字）
**分析时刻**：meta.context_as_of
```

`label` = 3.3 简报：大利空/大利好/利空/利好/轻空/轻多/·

### 4.5 LLM 参数

| 项 | 默认 |
|----|------|
| `temperature` | 0.3 |
| `max_tokens` | `min(12000, 2000 + holding×480 + candidate×360 + watch×180 + theme×80)` |
| `timeout_sec` | 180 |
| 空响应 | 重试 1 次 |

stance 计数来自 `prompt.stocks` 的 `stance_hint` / `primary_stance`。截断时 `truncated_suspected=true`。

---

## 五、4C · 后处理与落盘

### 5.1 拆分

`split_ai_report(raw)` → `(body, summary)`（`## 推送摘要` 为界）。

### 5.2 漏股校验

```text
parsed_codes = body 中 ### 后 6 位代码
expected = [s.code for s in prompt.stocks]
missing_codes = expected - parsed_codes
```

| 结果 | 行为 |
|------|------|
| `missing_codes` 空 | `synthesize.ok=true` |
| 非空 | `ok=warn`；含 holding/candidate → `critical_missing=true` |

### 5.3 预期 JSON

**路径**：`data/expectations/{target_trade_date}.json`  
`target_trade_date = next_trading_day(source_trade_date)`

```json
{
  "schema_version": 1,
  "source_trade_date": "2026-06-10",
  "target_trade_date": "2026-06-11",
  "saved_at": "ISO8601",
  "context_as_of": "…",
  "slot": "evening",
  "meta": {
    "l1_axes": "来自 market_local",
    "l2_mainlines": [],
    "constraints_applied": true
  },
  "stocks": {
    "600519": {
      "code": "600519",
      "name": "…",
      "primary_stance": "holding",
      "stance_label": "持仓",
      "groups": ["我的"],
      "short_expectation": "…",
      "expected_open": "偏高开|基准|偏低开|不确定",
      "discipline": "…",
      "message_net": "偏空|偏多|中性",
      "check_925": "…",
      "critical": []
    }
  },
  "missing_codes": [],
  "codes_analysis_order": []
}
```

| 规则 | 说明 |
|------|------|
| 键 | **`stocks[code]`**（白名单 31，不含 3.1 orphan） |
| 必解析 | holding + candidate + watch_right 的 `short_expectation` |
| theme_other | 有重大 label 或 AI 写了短线预期才入库 |
| 解析章 | 我的 / 想买的 / **观察** / 其它 |
| critical 兜底 | `events_by_code` 的 critical_* |
| meta | **`market_local`**，非老项目 `emotion_label` |

盘前 9:25 核对以 **我的 + 想买的** 为主；观察股可选展示。

### 5.4 AI 原文

`data/scheduled_ai/evening_{date}.json`：`raw`、`body`、`summary`、`model`、`missing_codes`、`truncated_suspected`。

`ai_digest/{date}/manifest.json` 追加 `stages.synthesize`。

---

## 六、4D · 可选校验

| 项 | 约定 |
|----|------|
| `evening.verify_enabled` | 默认 true |
| 事实库 | `stock_{code}.json` + `cls_{slot_key}.json` + `market_local` 结构化字段 |
| 不含 | market_l1/l2 AI narrative digest |
| 产出 | `ai_digest/{date}/verify.json` |
| fail | 不阻断落盘 |

---

## 七、CLI

```bash
python run.py preprocess --slot evening    # 3.1–3.8 → evening_context
python run.py generate --slot evening --phase ai
python run.py generate --slot evening --phase render
python run.py generate --slot evening        # 默认 ai → render
```

---

## 八、降级

| 场景 | 行为 |
|------|------|
| 无 `evening_context` | fail，提示先 preprocess |
| LLM 失败 | 不写 expectations |
| 无推送摘要 | `summary=""` |
| cls 4/5 / flow 失败 | 依 `constraints` 降权重 |
| 输出截断 | `truncated_suspected` + warn |

---

## 九、实现落点

| 模块 | 职责 |
|------|------|
| `packages/ai/llm.py` | `chat()` |
| `packages/ai/prompts.py` | `EVENING_SYSTEM`（ZXTT 补丁） |
| `packages/ai/parse.py` | `split_ai_report` |
| `packages/evening/prompt_build.py` | `build_evening_user_prompt` |
| `packages/evening/generate.py` | `run_evening_ai` |
| `packages/evening/expectations.py` | extract + save（code 键） |
| `packages/evening/verify.py` | 可选 4D |

---

## 十、验收（2026-06-10）

1. `evening_context` 存在；`prompt.stocks` = 31  
2. user prompt 顺序：priority → global → bundle → events → cls → stocks  
3. 正文 31 个 `###`；观察 15 只在「观察」章  
4. 摘要【我的】4、【想买的】12、【观察】15  
5. `expectations` 键为 code；meta 来自 `market_local`  
6. cls 4/5 不编造 `data_watch`

---

## 十一、定稿勾选

- [x] 主读 `prompt.*` 全结构（含 global 详情）  
- [x] 不重拼 snapshot / 不重跑 digest  
- [x] 对齐 3.3 label、3.4 双轴/镜头、3.5 constraints、3.6 reuse、3.8 cls  
- [x] 推送摘要含【观察】；31 只必写  
- [x] 预期 `stocks[code]`；漏股 `missing_codes`  
- [x] verify 仅 feeds+cls+market_local  
- [x] `generate --phase` 分界  

**第 4 步已定稿。**
