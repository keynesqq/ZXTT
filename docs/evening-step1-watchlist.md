# 第 1 步 · 自选世界（白名单 · 定稿）

> 步骤：**① / 5** · 开发总览：[`evening-dev.md`](evening-dev.md)  
> 位置：同花顺自选 → **第 1 步** → 第 2 步采集  
> 状态：**规格定稿**；CLI：`quote query --all`  
> 配置：[`evening-config.md`](evening-config.md) §`ths.analyze_blocks`  
> 后续：[`evening-step2-collect.md`](evening-step2-collect.md)  
> 更新：2026-06-10

## 一句话

从同花顺读取 **`ths.analyze_blocks` 白名单板块**内的股票，落成 `quote_query`：**31 只不重复 code** + **35 行板块归属**，供全链路分析（按 code）与展示（按 group）。

---

## 一、职责

| 做 | 不做 |
|----|------|
| 定「今晚分析哪些股」 | 拉公告/大盘/财联社（→②） |
| 定板块名与归属顺序 | 打标签/事件（→③） |
| 产出 `quote_query` 骨架 | AI 研判（→④） |

```text
同花顺 mo_*/block_*.blk
        ↓
ths.analyze_blocks.by_name
        ↓
quote query --all
        ↓
quote_query_{date}.json（quotes + memberships + structure）
        ↓
第 2 步采集（code 列表来源）
```

---

## 二、配置入口

`config.yaml` → `ths`（本地优先；`account_dir` 空则读 `legacy.zxreport_config`）：

```yaml
ths:
  account_dir: D:\同花顺软件\同花顺\mo_XXXXXXX
  analyze_blocks:
    by_name:
      - 我的
      - 想买的
      - 高度关注
      - 跌幅达到预期重点关注
```

| 键 | 含义 |
|----|------|
| `account_dir` | 同花顺账户目录（含 `block_*` 板块文件） |
| `analyze_blocks.by_name` | **白名单板块名**；顺序 = `structure.groups` 顺序 |

代码：`packages/watchlist/loader.py` → `load_stocks()`。

---

## 三、命令（第 1 步 = ① 的实操）

```bash
python run.py quote query --all
# 非交易日指定落盘日：
python run.py quote query --all --date 2026-06-10
```

终端应见：`code_count`、`row_count`、`groups`、`path`。

---

## 四、`quote_query` schema v2

路径：`data/quote_query_{calendar_date}.json`

| 字段 | 含义 |
|------|------|
| `schema_version` | `2` |
| `calendar_date` | 落盘日历日 |
| `updated_at` | 查询时刻 |
| `quotes[]` | **事实层**：按 **code 去重**（31 条）；每条含行情 46 字段 |
| `memberships[]` | **结构层**：`{code, name, group}`，同股多板块可重复（35 行） |
| `structure.groups[]` | 按配置顺序的板块索引 `{name, stocks[{code,name}]}` |
| `code_count` | 不重复只数（31） |
| `row_count` | 板块归属行数（35） |

**注意**：`quotes[]` 行内可有 `group` 字段（去重时保留 tier 更靠前板块），但 **③ 3.1 分析链路禁用 quote 行内 group**，归属只信 `memberships`。

---

## 五、31 code vs 35 row

| 概念 | 数量（2026-06-10） | 用途 |
|------|-------------------|------|
| `code_count` | 31 | ③④ 分析单元；每只 1 份 |
| `row_count` | 35 | ⑤ HTML 行情 Tab 行数 |

**双板块同股**（`memberships` 中 `groups[]` 长度 = 2）：

| code | 板块 |
|------|------|
| `600021` | 想买的 + 高度关注 |
| `300323` | 我的 + 想买的 |
| `603773` | 我的 + 想买的 |

**主镜头** `primary_stance`（③ 3.4）：`我的 > 想买的 > 观察 > 其它`（见 [`evening-config.md`](evening-config.md) §四）。

---

## 六、板块 → 镜头映射

| 板块名 | `primary_stance` | 推送章 |
|--------|------------------|--------|
| 我的 | `holding` | 【我的】 |
| 想买的 | `candidate` | 【想买的】 |
| 跌幅达到预期重点关注 | `watch_right` | 【观察】 |
| 高度关注 | `theme_other` | 【其它】（有重大事件时） |

2026-06-10 只数分布（定稿参考）：我的 4 · 想买的 12 · 观察 15 · 其它 4（高度关注）。

---

## 七、orphan code（白名单外）

公告/资讯查询若带上 **不在 `quotes` 白名单** 的 code，③ 3.1 记入 `meta.orphan_codes`，**不进 `by_code`**。

| 例 | 说明 |
|----|------|
| `600519` | 可能在 `news_query` 有行，但不在 31 只白名单 → orphan |

② 编排应用 **quote 的 31 code** 调 `announcement`/`news`，避免 orphan；历史脏数据由 ③ 隔离。

---

## 八、与第 2 步关系

| 规则 | 说明 |
|------|------|
| ② 前置 | 必须先有当日 `quote_query`（或 `--all` 作为 collect 第一步） |
| code 列表 | `quotes[].code` 去重 → 拼 `--codes` 给公告/资讯 |
| 板块顺序 | `structure.groups` → ⑤ `group_order` |

---

## 九、验收（2026-06-10）

| 检查 | 命令/文件 |
|------|-----------|
| 只数 | `quote query --all` → `code_count=31`, `row_count=35` |
| 板块 | `groups` 顺序：我的 → 想买的 → 高度关注 → 跌幅达到预期 |
| 文件 | `data/quote_query_2026-06-10.json` 中 `schema_version: 2` |
| 双板块 | `600021` 在 memberships 出现 2 次、group 不同 |

---

## 十、定稿勾选

- [x] `ths.analyze_blocks` 白名单  
- [x] schema v2 分层（quotes / memberships / structure）  
- [x] 31 code / 35 row 规则  
- [x] 主镜头优先级与板块映射  
- [x] orphan 隔离约定  

**第 1 步已定稿。**
