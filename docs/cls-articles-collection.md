# 财联社五篇固定长文采集方案

> 模块：`packages/market/cls/`（`collect` / `finance` / `daily_articles` / `request`）  
> 落盘：`data/cls_articles/{trade_date}.json`  
> 更新：2026-06-09（栏目 API 优先，弃用 400 ID 盲扫）

## 1. 要采哪五篇

每个**交易日**各一篇，发布日必须等于 `trade_date`：

| key | 栏目 | 标题识别规则 |
|-----|------|----------------|
| `daily_review` | 每日收评 | 以 `【每日收评】` 开头 |
| `data_watch` | 数据看盘 | 以 `【数据看盘】` 开头 |
| `focus_recap` | 焦点复盘 | 以 `【焦点复盘】` 开头 |
| `limit_up_analysis` | 当日涨停分析 | `M月D日涨停分析`，或 `【当日涨停分析】` / `【涨停分析】` 开头（排除 `【VIP】`） |
| `sentiment_hot` | 今日投资舆情热点 | `今日投资舆情热点`，或 `【今日投资舆情热点】` / `【投资舆情热点】` 开头 |

午盘两篇（涨停分析、舆情热点）ID 常低于收评，**不能仅靠首页猜 ID**。

## 2. 采集策略（核心）

**主路径：栏目 Subject API（秒级）**

并行请求财联社话题列表接口，一次拿最近 30 篇候选：

```
GET https://www.cls.cn/api/subject/{subject_id}/article
```

签名：`SHA1(排序后参数字符串) → MD5`，见 `web_sign_params()`。

| subject_id | 用途 |
|------------|------|
| **1103** | A股盘面直播（五篇常齐聚于此，**最关键**） |
| 1139 | 每日收评 |
| 1135 | 焦点复盘 |
| 1187 | 数据看盘 |

**辅路径：首页 Next.js**

抓取 `www.cls.cn` / `finance` / `depth` 页面 HTML，解析 `__NEXT_DATA__` 中的文章列表，与栏目 API 结果合并去重。

**兜底：小范围 ID 补扫**

仍缺篇时，仅在当日已知 ID 附近最多再试 **20** 个详情页（`stop_when_complete=True`），**不再扫 400 个**。

**正文：并行拉取**

五篇 ID 确定后，并行请求 `www.cls.cn/detail/{id}`，同样解析 `__NEXT_DATA__` → `articleDetail.content`，写入 `content` 字段（非仅链接）。

**默认关闭：AI 匹配**

`cls_articles_use_ai: false`。栏目 API 已能找齐五篇，AI 匹配慢且非必需。

## 3. 流程图

```
栏目 API（1103/1139/1135/1187 并行）
        ↓
首页 __NEXT_DATA__ 候选合并
        ↓
按标题 + 发布日匹配五 slot
        ↓
缺篇？→ 小范围 ID 补扫（≤20）
        ↓
并行拉 5 篇 detail 正文
        ↓
写入 data/cls_articles/{trade_date}.json
```

典型耗时：**3～10 秒**（网络正常时）。

## 4. 时效窗口

- 配置 `market.cls_articles_after`（默认 `20:00`，Asia/Shanghai）
- 当日 **20:00 前**：`articles_publish_ready()` 返回未就绪，采集 **skip**（不报错）
- 历史交易日、或当日已过窗口：正常采集
- 已齐 5 篇且未 `force`：读缓存，不重复联网

## 5. 配置（config.yaml）

```yaml
market:
  cls_articles_enabled: true          # 总开关
  cls_articles_evening_only: true     # 仅 evening 档位强制检查五篇
  cls_articles_after: "20:00"       # 当日可采时间窗
  cls_articles_use_ai: false          # 不用 AI 做栏目匹配
  cls_articles_id_scan_workers: 12  # 正文/补扫并行线程上限
```

## 6. 命令

```bash
# 财联社专用（推荐）：A 层看盘
python run.py cls collect --force --date 2026-06-09

# 财联社 A + B 五篇长文
python run.py cls collect --force --date 2026-06-09 --articles

# 大盘情绪（东财池 + 财联社，与上类似但含 AkShare）
python run.py market collect --force --date 2026-06-09 --articles

# 盘后场景 collect evening 会带 include_cls_articles=True
python run.py collect evening --force --date 2026-06-09
```

落盘：
- A 层：`data/cls_finance/{trade_date}.json`
- B 层：`data/cls_articles/{trade_date}.json`

## 7. 落盘结构

`data/cls_articles/2026-06-09.json` 关键字段：

- `found_count` / `expected_count`：应为 5 / 5
- `articles.{slot_key}.content`：**正文**（AI 读此字段，不是 `url`）
- `articles.{slot_key}.content_chars`：正文字数
- `articles.{slot_key}.published_at`：发布时间（校验用）
- `warnings`：缺篇或正文失败时列出

同时可嵌入 `data/market_sentiment/{trade_date}.json` → `cls.daily_articles`。

## 8. AI 如何使用

`format_cls_articles_prompt()` 读取落盘 JSON，每篇 `content` 截取前 **1200 字**，拼入报告提示词的 `[财联社固定栏目]` 段。  
要求模型**仅引用已标注发布时间的当日栏目**，勿编造收评/复盘。

## 9. 验收

```bash
# 1. 采集
python run.py market collect --force --date 2026-06-09 --articles

# 2. 检查落盘
# data/cls_articles/2026-06-09.json → found_count=5，五篇均有 content

# 3. health（evening）
python run.py collect health --slot evening --date 2026-06-09
# cls_articles 应为 ok
```

## 10. 搜索页方案（已验证不可行）

用户提供的链接形态：

```
https://www.cls.cn/searchPage?keyword={URL编码关键词}&type=depth
```

示例：[每日收评深度搜索](https://www.cls.cn/searchPage?keyword=%E6%AF%8F%E6%97%A5%E6%94%B6%E8%AF%84&type=depth)

**实测结论（2026-06-09）**：浏览器里「排第一位即目标」的思路成立，但 **无法用当前项目的 `httpx` 直连复现**：

| 现象 | 说明 |
|------|------|
| 无 `__NEXT_DATA__` | 返回页是空壳 + 反爬脚本，不含文章列表 |
| 关键词不在 HTML | `keyword` 仅存在于 URL，服务端不嵌入结果 |
| WAF 门禁 | 页内脚本做浏览器指纹 → 写 `wafatclconfirm` Cookie → 再跳转 `security_antibot_code=...` 才进真页面 |
| 试探 API 均失败 | `/api/search/article`、`/nodeapi/search/article` 404；`/api/sw` POST 404 |

要走搜索页，需 **Playwright 等浏览器自动化** 跑完整 WAF + 渲染，慢、脆、与「3 分钟内采齐」目标冲突。

**因此主路径仍为 §2 栏目 Subject API（1103 等）**，搜索页仅作备忘，不接入采集代码。

## 11. 勿回退的方案

以下方式已证实**慢或不全**，勿再作为主路径：

| 方案 | 问题 |
|------|------|
| 仅首页 `__NEXT_DATA__` | 常只露出 2～3 篇 |
| 400 ID 盲扫 | 几分钟仍可能缺篇 |
| 旧接口 `v1/roll/get_roll_list` | 已 404 |
| 默认 AI 匹配 | 多一次 LLM 调用，无必要 |

## 12. 代码入口

| 函数 | 说明 |
|------|------|
| `collect_cls_daily_articles()` | 采集主入口 |
| `discover_subject_candidates()` | 栏目 API 并行发现 |
| `discover_matched_articles()` | 匹配 + 小范围补扫 |
| `_fetch_matched_contents()` | 并行拉正文 |
| `fetch_article_detail()` | 单篇 detail 页解析 |
| `format_cls_articles_prompt()` | 拼 AI 提示词 |
