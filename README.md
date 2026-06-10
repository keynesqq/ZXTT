# ZXTT

A 股数据采集工具集，**8 个模块**经 `run.py` 统一调用。模块说明见 [`docs/packaged-modules.md`](docs/packaged-modules.md)（以 `run.py` 现有命令为准）。

## 安装

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy config.example.yaml config.yaml
```

`config.yaml` 可只配 `legacy.zxreport_config` 指向老项目 `ZXReport/config.yaml`，只读复用同花顺路径与自选板块。

## 八个命令

| 模块 | 命令 |
|------|------|
| 财联社 | `python run.py cls collect --articles` |
| 行情查询 | `python run.py quote query --codes 600519` |
| 公告查询 | `python run.py announcement query --codes 600519` |
| 集合竞价 | `python run.py auction --codes 600519` |
| 资讯查询 | `python run.py news query --codes 600519` |
| 大盘短线生态 | `python run.py ecosystem collect` |
| 指数快照 | `python run.py index collect` |
| 大盘资金流 | `python run.py flow collect` |

`market collect` 为 `ecosystem collect` 的兼容别名。`market collect --articles` 已废弃，请改用 `cls collect --articles`。

## 盘后采集（手动顺序）

无 `collect evening` 编排命令，建议按序执行：

```bash
python run.py ecosystem collect
python run.py cls collect --articles
python run.py index collect
python run.py flow collect
```

非交易日加 `--force --date YYYY-MM-DD`。

## 晚间报告（规划中）

22 点「明日作战卡」**开发主文档**：[`docs/evening-dev.md`](docs/evening-dev.md)（五步对齐、数据路径、实现落点）。精简总览：[`evening-pipeline.md`](docs/evening-pipeline.md)。

规划命令：`collect --slot evening` → `preprocess --slot evening` → `generate --slot evening`（尚未实现）。

## 测试

```bash
python -m unittest discover -s tests -v
```

## 产出目录

运行时 JSON 写入 `data/`（如 `cls_finance/`、`market_flow/`、`quote_query_{date}.json` 等）。
