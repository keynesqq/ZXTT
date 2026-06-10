# 22 点晚间报告管线（精简总览）

> **开发主文档**：[`evening-dev.md`](evening-dev.md)（五步对齐 + 数据路径 + 实现落点 + 验收）  
> 运维：[`evening-runbook.md`](evening-runbook.md) · 状态：规格定稿，代码待实现  
> 更新：2026-06-10

## 产品一句话

交易日 22:00「明日作战卡」：大盘 + 主线 + 自选 31 只研判 → HTML、微信简报、明日预期。无竞价。

## 五步

| 步 | CLI（规划） | 详文 |
|----|-------------|------|
| ① 自选 | `quote query --all` | [step1](evening-step1-watchlist.md) |
| ② 采集 | `collect --slot evening` | [step2](evening-step2-collect.md) |
| ③ 预处理 | `preprocess --slot evening` | [step3](evening-step3-preprocess.md) |
| ④ AI | `generate --phase ai` | [step4](evening-step4-ai.md) |
| ⑤ 触达 | `generate --phase render` | [step5](evening-step5-render.md) |

硬规则、子步 3.1–3.8、配置、Prompt、样例、页面线框见 **[`evening-dev.md`](evening-dev.md)**。
