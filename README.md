# ZXTT

从 [ZXModular](D:\ZXModular) 迁出的**已打包 8 模块**工具集。老仓 `ZXModular` 已归档，日常开发在本项目。

模块说明见 [`docs/packaged-modules.md`](docs/packaged-modules.md)。

## 安装

```bash
cd D:\ZXTT
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy config.example.yaml config.yaml
```

`config.yaml` 可只配 `legacy.zxreport_config: D:\ZXReport\config.yaml`，只读复用老项目同花顺路径与自选板块。

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

## 测试

```bash
python -m unittest tests.test_market tests.test_market_index tests.test_market_flow tests.test_auction tests.test_quote_query tests.test_quote_query_cache tests.test_announcement_query tests.test_news_query tests.test_query_cache -v
```

## 产出目录

运行时 JSON 写入 `data/`（如 `cls_finance/`、`market_flow/`、`quote_query_{date}.json` 等）。
