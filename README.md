# Research Radar · 医学科研雷达

> 把重点期刊、医学新闻、卫生机构动态和近一年专题热点汇成一份可追溯周报，
> 再用 DeepSeek 提炼对传染病流行病学与数据驱动医学研究真正有用的问题。

Research Radar 是一个公开、无图片、可追溯的医学科研情报系统。它每周一
北京时间 05:33 自动运行，同时生成 Markdown 周报、GitHub Pages 网页、
JSON manifest、R2 原始数据归档和邮件。

- 在线周报：[Research Radar Pages](https://rayeruixinzhang.github.io/Research-Radar/)
- 历史报告：[`reports/`](reports/)
- 逐期追溯清单：[`manifests/`](manifests/)
- 部署说明：[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)

## 一眼看懂五个板块

| 板块 | 回答的问题 | 时间范围 | 核心数据来源 | 数量上限 |
|---|---|---:|---|---:|
| **1. CNS期刊近期论文** | CNS及高水平医学期刊本周有哪些重要原创研究？ | 上一自然周 | PubMed；Europe PMC、OpenAlex补充元数据 | 15篇 |
| **2. 医学与公共卫生新闻** | 儿童健康、传染病和医院服务有哪些重要现实事件？ | 上一自然周 | Reuters、AP、BBC、Guardian、STAT、CIDRAP、KFF、Medical Xpress、澎湃、新华网 | 10条 |
| **3. 卫生机构动态** | WHO及主要国家发布了哪些预警、指南和政策？ | 上一自然周；真实空结果时依次回退14/30天并显式标记 | WHO、CDC/MMWR/HHS、PHAC、国家卫健委/中国CDC、UKHSA/NHS、ECDC、澳大利亚卫生部、PAHO | 10条 |
| **4. 近一年专题科研热点** | 哪些儿童感染临床流行病学方向适合继续形成博士课题？ | 最近365天 | PubMed/MEDLINE + SCImago Medicine Q1；DeepSeek批量增强 | 最多2,000条候选，展示10个热点 |
| **5. 跨板块科研启发** | 四类信号如何转化为研究问题和方法？ | 基于本期板块1–4 | DeepSeek Flash + 本期结构化输入 | 1份结构化分析 |

```mermaid
flowchart LR
    A["重点期刊论文"] --> E["结构化周报"]
    B["医学与公卫新闻"] --> E
    C["卫生机构动态"] --> E
    D["近一年专题热点"] --> E
    E --> F["DeepSeek 跨板块分析"]
    E --> G["Markdown / Pages / 邮件"]
    F --> G
    E --> H["manifest + R2 追溯"]
    F --> H
```

## 聚焦领域

系统重点识别并标注以下方向：

- 流行病学、疾病监测、暴发调查和风险预测；
- 传染病、感染、病原体、疫情与大流行；
- 公共卫生、人口健康、健康政策和健康公平；
- 儿科学、新生儿与儿童健康；
- 呼吸道疾病、肺炎、流感、哮喘和慢阻肺；
- 疫苗、免疫接种、效果与安全性；
- 医院感染、感染控制和抗微生物药物耐药；
- AI/机器学习与疾病监测、预警、预测模型的交叉研究。

板块1负责广泛发现，不要求论文同时命中儿科、感染、AI和预测等关键词；
板块4则采用儿童人群 × 感染疾病 × 研究问题的强约束检索轨道。

## 板块4如何筛选近一年热点

板块4不是“整个PubMed近一年全部医学论文”，而是一个透明、受控的专题样本：

1. 在PubMed检索最近365天的 `MEDLINE` 子集；
2. 分别检索临床表型、严重结局预测、24–48小时动态恶化、病毒×宿主表型、
   模型外部验证、复杂慢性病儿童和严重呼吸道病毒七条研究轨道；
3. 合并并去重各轨道结果，当前每次回填最多保留2,000条候选记录；
4. 仅保留具有DOI、未标记撤稿、且ISSN匹配
   **SCImago 2025 Medicine Q1** 的论文；
5. 排除成人COPD/哮喘、肺癌、普通影像AI、手术/心血管/肿瘤预测等无明确可迁移价值的内容；
6. OpenAlex提供标准化引用指标，MeSH作为医学标签；
7. 每条研究轨道至少包含2篇论文后参与排名，并始终保留确定性回退分析。

热点分数：

`研究方向匹配度 30% + 方法创新 20% + 临床价值 20% + 近90天趋势 15% + 标准化引用 10% + 多中心/外部验证 5%`

报告展示前10个方向，每个方向包含趋势、研究设计、常用方法、最多3篇代表论文、
Research Gap和Potential PhD Question。DeepSeek只分析Python筛选后的代表性论文，
采用独立提示词、token上限、批次和缓存；API失败时回退到确定性分析，不会让板块4为空。
完整检索式和筛选词保存在
[`config/settings.yaml`](config/settings.yaml)，每期manifest同时保存口径版本。

> **重要：SCImago Q1 不等同于 JCR Q1。** 本项目明确使用可公开复核的
> SCImago Medicine Q1替代口径，不会将其标注为JCR分区。

## 板块5能做什么

DeepSeek只读取板块1–4已经展示的标题、短摘要、标签和来源标识，生成：

1. 四板块综合研判；
2. 对传染病流行病学的启示；
3. 可检验的数据驱动医学研究问题；
4. 候选研究方法与数据需求；
5. 证据局限、偏倚与可推广性提醒。

每项分析必须引用输入中的证据编号；程序会丢弃模型虚构的编号，并将有效编号
链接回DOI或原始页面。提示词位于
[`prompts/cross_board_analysis_zh.md`](prompts/cross_board_analysis_zh.md)，
模型、提示词版本、输入SHA-256、条目数量和token用量都会写入manifest。

## 数据追溯

```text
原始响应（gzip JSON，R2）
        ↓ SHA-256 / R2对象键
SQLite标准化记录
        ↓ item_id / DOI / URL / content_hash
周报 Markdown + Pages
        ↓ Git提交 / Actions Run ID
manifest/YYYY/YYYY-Www.json
```

- 论文以标准化DOI去重，新闻优先使用canonical URL；
- 新闻和机构动态只保存标题、原始链接、发布日期及不超过250字符的摘要；
- 不保存新闻全文，不在周报中放置图片；
- 板块1论文必须有可点击DOI或PMID，板块4代表性论文必须有DOI；新闻和机构内容必须有原始链接；
- 单个来源失败时继续生成周报并在“数据源运行状态”中标注。

## 快速开始

```powershell
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"

python -m research_radar doctor
python -m research_radar import-scimago "incoming\scimagojr.csv"
python -m research_radar backfill --days 365 --retmax 2000
python -m research_radar collect --days 7
python -m research_radar build-report
pytest
```

固定CLI：

- `python -m research_radar backfill --days 365`
- `python -m research_radar collect --days 7`
- `python -m research_radar build-report --send-email`
- `python -m research_radar doctor`

## 自动部署

工作流位于 [`.github/workflows/research-radar.yml`](.github/workflows/research-radar.yml)：

- 每周一北京时间05:33自动运行；
- 每次运行均刷新七条研究轨道的365天热点语料，并支持手动周报；
- 自动恢复/上传R2 SQLite数据库；
- 自动提交周报与manifest；
- 自动发布GitHub Pages并发送163邮箱。

Secrets配置见[部署说明](docs/DEPLOYMENT.md)，密钥不得写入代码、报告或Issue。

## 使用时必须知道的限制

- 板块4当前有2,000条候选上限，因此代表“专题聚焦样本”，不是近一年全部Q1论文；
- PubMed/MEDLINE之外的论文可能遗漏；ResearchGate不自动抓取，Web of Science/JCR
  适配器尚未启用；
- GDELT用于发现缺少稳定RSS的页面，可能受限流、索引延迟和域名覆盖影响；
- 摘要来自公开元数据，可能缺失或晚于出版时间更新；
- 板块4是预设研究轨道上的聚焦样本，Research Gap仅代表本次检索到的文献，不是系统综述结论；
- DeepSeek输出是研究启发而非系统综述、因果结论或临床建议，必须回到原文核查；
- 来源状态、API价格、网页结构和期刊分区会变化，应定期审计配置。

## 许可证与来源

本项目参考并衍生自GPLv3项目
[TrendRadar](https://github.com/sansan0/TrendRadar)，以
GPL-3.0-or-later发布。详见 [`LICENSE`](LICENSE) 与 [`NOTICE`](NOTICE)。
