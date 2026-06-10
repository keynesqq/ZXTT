# 第 5 步 · HTML 页面线框（MVP 三 Tab）

> 开发总览：[`evening-dev.md`](evening-dev.md) · ⑤逻辑：[`evening-step5-render.md`](evening-step5-render.md)  
> 对照：`D:\ZXReport\templates\daily_report.html` · 更新：2026-06-10

## 一句话

晚间报告 **3 个 Tab**（研判 / 行情 / 素材），顶栏展示数据健康与 31/35；快照代码链到 AI 正文 `#stock-{code}`。

---

## 一、页面总览

```text
┌─────────────────────────────────────────────────────────────┐
│  ZXTT 明日作战卡 · 2026-06-10                                │
│  分析时刻 22:15 · 31 只分析 · 35 行板块 · 财联社 4/5         │
│  ⚠ 大盘主力缺失；北向可疑                                    │
├─────────────────────────────────────────────────────────────┤
│  [ 研判 ]  [ 行情快照 ]  [ 素材 ]          ← MVP 无「设置」Tab │
├─────────────────────────────────────────────────────────────┤
│                     （当前 Tab 内容区）                       │
└─────────────────────────────────────────────────────────────┘
```

**产出路径**：`reports/{date}/daily_evening.html`（`index.html` 可跳转同页）。

---

## 二、顶栏 `report_header`

| 元素 | 数据字段 | 展示规则 |
|------|----------|----------|
| 主标题 | `trade_date` | `ZXTT 明日作战卡 · {date}` |
| 副标题 | `context_as_of` | `分析时刻 {context_as_of}` |
| 规模 | `code_count` / `row_count` | `31 只分析 · 35 行板块` |
| 财联社 | `cls_articles_found` | `财联社 4/5`；`complete=false` 时 ⚠ |
| 健康 | `health_brief` | 一行人话；`trust_flags` 关键项 |
| AI 状态 | `ai_ok` / `missing_codes` | 漏股 warn；`truncated_suspected` 黄标 |
| 校验 | `verify.overall` | 可选小字 |
| 预期脚注 | `expectations_path` | `明日预期 → data/expectations/…` 链接文案 |

---

## 三、Tab 1 · 研判 `panel-analysis`

自上而下区块顺序：

```text
1. 推送摘要盒（ai_summary_html）
2. AI 正文（ai_body_html，带锚点）
3. 重大事件区（events_by_code，按 code 去重）
4. 大盘摘要条（可折叠：l1_brief / l2_brief / constraints）
5. Digest 附录（cls 五栏 + feeds 汇总）
```

### 3.1 推送摘要盒

```text
┌─ 推送摘要 ─────────────────────────────────┐
│ 【环境】…                                   │
│ 【仓位】…                                   │
│ 【我的】大利空 600xxx … | 守 | …            │
│ 【想买的】…                                 │
│ 【观察】· 301293 … | 观察 | …   ← ZXTT 必含 │
│ 【其它】无                                  │
│ 【操作】…                                   │
│ 分析时刻：2026-06-10 22:15                  │
└────────────────────────────────────────────┘
```

解析器须支持 **中文六档 label**（大利空…轻多）与 **【观察】**（迁 `push_summary_format` 并扩展）。

### 3.2 AI 正文

- 来源：`scheduled_ai.body` → Markdown → HTML  
- 每个 `### {code} {name}` 外包 `<h3 id="stock-{code}">`  
- 章标题按 stance：我的 / 想买的 / **观察** / 其它（与第 4 步一致）

### 3.3 重大事件区

```text
┌─ 重大事件（按股票，不重复）──────────────────┐
│ 301293 三博脑科  [跌幅达到预期重点关注]       │
│   [利空] 股东拟减持…  2026-06-10             │
│ 600021 上海电力  [想买的 · 高度关注]          │
│   无规则命中                                  │
└────────────────────────────────────────────┘
```

| Badge class | label |
|-------------|-------|
| `badge-critical-bear` | 大利空 |
| `badge-critical-bull` | 大利好 |
| `badge-bear` | 利空 / 轻空 |
| `badge-bull` | 利好 / 轻多 |
| `badge-unverified` | 待核实后缀 |

数据源：`events_by_code[code].display[]`（≤3），附 `groups[]` 文本。

### 3.4 大盘摘要条（`<details>` 可折叠）

```text
▶ 大盘环境（本地 L1/L2）
  L1：池子中性；指数分化…
  L2：主线电力设备…
  写作约束：禁编造大盘主力…
```

### 3.5 Digest 附录

```text
▶ 预消化资料
  · 每日收评 [ok] summary…
  · 数据看盘 [missing] …
  · feeds：refresh 3 / reuse 28 / failed 0
```

---

## 四、Tab 2 · 行情快照 `panel-snapshot`

### 4.1 板块子 Tab

顺序 = `evening_context.group_order`（**不可拖拽**，与老项目素材 Tab 同步口径一致）：

```text
[ 我的(4) ] [ 想买的(12) ] [ 高度关注(4) ] [ 跌幅达到预期(15) ]
```

### 4.2 表格列（每板块一张表，合计 35 行）

| 列 | 内容 |
|----|------|
| 代码 | `<a href="#stock-{code}">600021</a>` |
| 名称 | |
| 今% | 着色涨跌 |
| 5日/20日 | |
| 主力 | `main_net_yi` |
| 标签 | `local_block.tags[]` ≤5 |
| 事件 | `events_label`（大利空…·） |
| 镜头 | `stance_label`（持仓/候选/观察/其它） |

同股第二行（另一 group）：代码仍链同一 `#stock-{code}`；可选提示「主分析见观察章」。

### 4.3 对照老项目

迁 `partials/snapshot_grouped_table.html` + 精简版 `snapshot_tabs_script`（**去掉拖拽排序**）。

---

## 五、Tab 3 · 素材 `panel-materials`

### 5.1 默认 slim（无 `evening_bundle_full`）

按 **code** 折叠列表（顺序建议 = `codes_analysis_order`）：

```text
▶ 600021 上海电力 [候选]  feeds: reuse
    summary: …
    facts: …
    context_note: 无新公告资讯，沿用 2026-06-08 digest
    events_display: (≤3)
```

### 5.2 审计模式（有 `evening_bundle_full`）

板块子 Tab + 全量公告/资讯列表；迁 `feeds_grouped_panel.html`。

---

## 六、无 AI 降级页

| 条件 | 研判 Tab |
|------|----------|
| 有 `evening_context`，无 `scheduled_ai` | 黄框：「AI 未生成，请运行 `generate --phase ai`」 |
| 有 `ai_error` | 红框展示错误 |
| 行情/素材 Tab | **正常渲染** |
| 微信 | **不推送** |

---

## 七、模板文件规划

```text
templates/
├── daily_evening.html          # 主壳：顶栏 + 3 Tab
└── partials/
    ├── evening_header.html
    ├── evening_analysis_panel.html
    ├── evening_events_block.html
    ├── evening_market_bar.html
    ├── evening_digest_appendix.html
    ├── evening_snapshot_panel.html   # 迁 snapshot_grouped_table
    ├── evening_materials_slim.html
    └── evening_styles.html
```

| 老项目 partial | ZXTT |
|----------------|------|
| `spa_nav` 四 Tab | 三 Tab，无 settings |
| `scheduled_ai` 多份 details | 单份 `evening_{date}.json` 展开 |
| ⛔/★ badge | 中文六档 label |
| `digest_appendix` | 仅 cls + feeds（无 market_l1/l2 AI） |

---

## 八、交互要点

| 交互 | 行为 |
|------|------|
| 快照点代码 | 切到研判 Tab + `location.hash=#stock-{code}` + scroll |
| Tab 切换 | 纯 CSS/JS，无后端 |
| 外链 | 公告/资讯 `target=_blank` |

**MVP 不做**：设置页、盘中刷新、竞价、live、SPA 历史 AI 列表。

---

## 九、验收（对照 2026-06-10）

1. 顶栏显示 `31 只 · 35 行`、`财联社 4/5`  
2. 行情 Tab 四板块共 35 行，顺序与 config 一致  
3. 点击 `301293` 跳到正文对应 `###`  
4. 研判区摘要含【观察】15 条（有 AI 时）  
5. 无 `scheduled_ai` 时研判区降级、行情 Tab 仍有数据  

---

## 十、定稿勾选

- [x] MVP 三 Tab 线框  
- [x] 顶栏字段清单  
- [x] 事件 badge 与 code 去重  
- [x] 快照锚点与列定义  
- [x] slim 素材区  
- [x] 无 AI 降级  
- [x] partial 迁移对照  

**页面线框已定稿。**
