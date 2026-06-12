# ZXTT

A 股数据采集工具集，**9 个基础采集模块** + **午间 / 晚间报告**经 `run.py` 统一调用。模块说明见 [`docs/packaged-modules.md`](docs/packaged-modules.md)。

## 安装

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy config.example.yaml config.yaml
```

`config.yaml` 可只配 `legacy.zxreport_config` 指向老项目 `ZXReport/config.yaml`，只读复用同花顺路径与自选板块。

## 九个命令

| 模块 | 命令 |
|------|------|
| 财联社 | `python run.py cls collect --articles` |
| 行情查询 | `python run.py quote query --codes 600519` |
| 公告查询 | `python run.py announcement query --codes 600519` |
| 集合竞价 | `python run.py auction --codes 600519` |
| **盘中分钟序列** | `python run.py intraday` |
| 资讯查询 | `python run.py news query --codes 600519` |
| 大盘短线生态 | `python run.py ecosystem collect` |
| 指数快照 | `python run.py index collect` |
| 大盘资金流 | `python run.py flow collect` |

`market collect` 为 `ecosystem collect` 的兼容别名。`market collect --articles` 已废弃，请改用 `cls collect --articles`。

**全天监控 `intraday`**（默认全自选、同股只采一次）：9:15 竞价（独立文件供早盘报告）→ 9:30–11:30 / 13:00–15:00 正式交易分段合并。计划任务见 `scripts/run_intraday_watch.bat`。验通路：`python run.py intraday --simulate`；挂掉续跑：`python run.py intraday --resume`。详文见 [`docs/packaged-modules.md`](docs/packaged-modules.md) §5。

## 盘后采集（手动顺序）

仅采大盘事实、不生成报告时，按序执行：

```bash
python run.py ecosystem collect
python run.py cls collect --articles
python run.py index collect
python run.py flow collect
```

非交易日加 `--force --date YYYY-MM-DD`。

## 22 点晚间报告

一键跑通（自动打开浏览器进度页 → 完整作战卡 + 微信）：

```bash
python run.py evening
python run.py evening --date 2026-06-10
```

分步调试：`collect --slot evening` → `preprocess --slot evening` → `generate --slot evening`  
详文：[`docs/evening-dev.md`](docs/evening-dev.md) · 配置：[`docs/evening-config.md`](docs/evening-config.md)

## 午间报告（约 12:50）

与晚间完全独立；一键跑通（自动打开进度页 → 午间作战卡 + 微信）：

```bash
python run.py midday
python run.py midday --date 2026-06-10
```

分步调试：`collect --slot midday` → `preprocess --slot midday` → `generate --slot midday`  
详文：[`docs/midday-dev.md`](docs/midday-dev.md)

## 早盘集合竞价报告（约 9:25）

与晚间、午间独立；9:15 并行跑 `auction` + `morning --phase pre`，9:25 出报告：

```bash
python run.py morning --phase pre
python run.py morning
python run.py morning --date 2026-06-10
```

详文：[`docs/morning-dev.md`](docs/morning-dev.md)

## 测试

```bash
python -m unittest discover -s tests -v
```

## 产出目录

运行时 JSON 写入 `data/`（如 `cls_finance/`、`market_flow/`、`quote_query_{date}.json`、`intraday_series_{date}.json` 等）。
