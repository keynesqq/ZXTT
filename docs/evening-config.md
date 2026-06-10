# 22 点晚间报告 · 配置说明

> 开发总览：[`evening-dev.md`](evening-dev.md) · 样例：[`config.example.yaml`](../config.example.yaml)  
> 关联：step2–5 详文 · 更新：2026-06-10

## 一句话

晚间管线专用键集中在 **`evening:`**；自选板块、公告资讯回溯、LLM 等多数**继承**本地配置或 `legacy.zxreport_config` 指向的老项目 `config.yaml`。

---

## 一、配置加载顺序

```text
ZXTT config.yaml
    ├── 本地段优先（ths / quote / feeds / evening / wechat …）
    └── legacy.zxreport_config → 只读合并（ths、market、feeds、llm 等缺省时）
```

实现参考：`packages/core/config.py`（`ths_cfg`、`feeds_cfg`、`market_cfg` 等）。

---

## 二、`evening:` 晚间管线

| 键 | 类型 | 默认 | 用于哪步 | 业务含义 |
|----|------|------|----------|----------|
| `feeds_digest_workers` | int | `4` | ③ 3.6 | 个股 feeds AI digest 并发数；上限 16 |
| `on_digest_fail` | str | `degrade` | ③ 3.6 | `degrade`：失败 code 标 failed，其余继续；`abort`：任一只失败终止 6B |
| `cls_digest_workers` | int | `3` | ③ 3.8 | 财联社 B 层并发；上限 3 |
| `cls_short_local_threshold` | int | `200` | ③ 3.8 | 单篇 `content_chars` 低于此值可走本地短摘要，不调 LLM |
| `cls_digest_max_tokens` | int | `2500` | ③ 3.8 | 单篇 cls digest LLM max_tokens |
| `verify_enabled` | bool | `true` | ④ 4D | 合成后可选事实校验（feeds+cls+market_local） |
| `write_bundle_full` | bool | `false` | ③ 3.7 | 是否额外写 `evening_bundle_full.json` 审计包 |
| `preprocess_cls_recollect` | bool | `true` | ③ 3.8 | `preprocess --slot evening` 前是否重采 `cls collect --articles` |

---

## 三、`events:` 规则事件（③ 3.3）

可与老项目 `events:` 对齐；未配置时用代码内默认词表。

| 键 | 类型 | 默认 | 含义 |
|----|------|------|------|
| `enable_medium` | bool | `true` | 是否启用轻空/轻多档 |
| `display_max` | int | `3` | 每只展示事件条数上限（简报/3.7） |
| `lookback_days` | int | `3` | 待核实/减持印证窗口；与 `feeds.announcement.lookback_days` 对齐 |

词表覆盖（可选）：`critical_bear`、`critical_bull`、`high_bear`、`high_bull`、`medium_bear`、`medium_bull` 字符串数组。

详见 [`evening-step3-preprocess.md`](evening-step3-preprocess.md) §3.3。

---

## 四、`ths.analyze_blocks` ↔ 镜头

| 同花顺板块名（`by_name`） | `primary_stance` | `stance_label` | 优先级 |
|---------------------------|------------------|----------------|--------|
| 我的 | `holding` | 持仓 | 1 |
| 想买的 | `candidate` | 候选 | 2 |
| 跌幅达到预期重点关注 | `watch_right` | 观察 | 3 |
| 高度关注 | `theme_other` | 其它 | 4 |
| （其它板块名） | `theme_other` | 其它 | 4 |

- `quote query --all` 只拉 `analyze_blocks.by_name` 所列板块内股票。  
- 同股多板块：`groups[]` 全保留；**主镜头**按上表优先级取最高档。  
- 板块顺序 → `structure.groups` → 第 5 步 Tab 顺序。

配置示例见 `config.example.yaml` → `ths.analyze_blocks`。

---

## 五、`wechat:` 微信（⑤）

| 键 | 类型 | 默认 | 含义 |
|----|------|------|------|
| `enabled` | bool | `false` | 第 5 步是否推送 `scheduled_ai.summary` |
| `webhook_url` | str | `""` | 企业微信机器人 URL（或读环境变量，实现时定） |
| `title_prefix` | str | `ZXTT 盘后` | 推送标题前缀 |

推送**仅第 5 步**；第 4 步不落盘 push。详见 [`evening-step5-render.md`](evening-step5-render.md) §5C。

---

## 六、继承自老项目 / 本地段（非 `evening:` 但晚间必用）

| 段 | 晚间用途 | ZXTT 读取方式 |
|----|----------|---------------|
| `legacy.zxreport_config` | 指向 `D:\ZXReport\config.yaml` | `legacy_config_path()` |
| `ths.account_dir` | 同花顺自选路径 | `ths_cfg()`，本地空则读 legacy |
| `quote.*` | 双源行情校验 | `quote_cfg()` |
| `feeds.announcement` | 公告回溯天数 | `feeds_cfg()` |
| `news.*` / `feeds.news` | 资讯回溯、并发 | `news_cfg()` |
| `market.*` | cls / index 开关 | `market_cfg()` 合并 legacy |
| `flow.*` | 资金流、自选主力 | `flow_cfg()` |
| `llm.*` | 模型、max_tokens | **实现时**从 legacy 读（ZXTT 本地可覆盖） |

### `llm:`（老项目典型键）

| 键 | 含义 | 晚间用法 |
|----|------|----------|
| `max_tokens` | 单次合成上限 | ④ 合成正文 |
| `group_max_tokens` | 分组上限 | ④ 长报告 |
| API 密钥 | 环境变量 / legacy | ④ ③ digest |

ZXTT `config.example.yaml` 不重复密钥；开发机通过 `legacy.zxreport_config` + `.env` 提供。

---

## 七、与八模块配置交叉索引

| 采集模块 | 主要配置段 | 文档 |
|----------|------------|------|
| quote | `ths`, `quote` | packaged-modules §2 |
| announcement | `feeds.announcement` | §3 |
| news | `news`, `feeds` | §5 |
| ecosystem | `market` | §1 |
| index | `index`, `market.index_enabled` | §6 |
| flow | `flow` | §7 |
| cls | `market.cls_*` | §1 |

---

## 八、验收

1. 打开 `config.example.yaml`，存在 `evening:`、`events:`、`wechat:` 注释块  
2. `ths.analyze_blocks.by_name` 含 4 个板块名，与 step3 镜头表一致  
3. 改 `evening.feeds_digest_workers` 不影响其它模块命令  
