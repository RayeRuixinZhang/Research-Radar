# Research Radar

Research Radar 是一个公开、可追溯的医学科研情报周报系统。它每周汇总：

1. 过去 365 天 SCImago Medicine Q1（非 JCR）科研热点；
2. 医学、公共卫生、卫生服务、传染病与医疗 AI 新闻；
3. WHO 及主要国家卫生机构动态；
4. 四大医学期刊和 Nature / Science / Cell 系列重点论文；
5. 可插拔的跨板块 AI 科研启发（首版默认关闭）。

报告不包含图片，不保存新闻或论文全文。每条论文必须包含 DOI，每条新闻
和机构动态均链接到原始页面。

## 快速开始

```bash
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"
python -m research_radar doctor
python -m research_radar import-scimago incoming/scimagojr.csv
python -m research_radar collect --days 7
python -m research_radar backfill --days 365
python -m research_radar build-report
pytest
```

## 自动部署

`.github/workflows/research-radar.yml` 每周一北京时间 05:33 运行，也支持
手动触发。工作流会采集、生成 Markdown/manifest、提交历史、发布 GitHub
Pages，并在 SMTP Secrets 完整时发送邮件。

需要配置的 Secrets 见 [部署文档](docs/DEPLOYMENT.md)。

## 数据口径

- PubMed、Europe PMC、Crossref 和 OpenAlex 用于论文元数据。
- ResearchGate 不进行自动抓取。
- 从 SCImago 下载最新版 Medicine CSV 后，可直接运行
  `python -m research_radar import-scimago <CSV路径>`。导入器兼容官方列名和
  逗号、分号或 Tab 分隔格式，自动筛选 Q1、规范化 ISSN，并记录原文件
  SHA-256；无需手工改表头。未导入时板块 1 会明确标记为不可用，绝不冒充
  JCR Q1。
- 新闻只保存短摘要和原始链接，不缓存全文。

## 许可证

本项目参考并衍生自 GPLv3 项目
[TrendRadar](https://github.com/sansan0/TrendRadar)，以 GPL-3.0-or-later
发布。详见 `LICENSE` 与 `NOTICE`。
