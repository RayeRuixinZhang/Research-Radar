# 部署说明

## GitHub Secrets

| Secret | 必需 | 用途 |
|---|---:|---|
| `OPENALEX_API_KEY` | 建议 | OpenAlex 免费 API Key |
| `DEEPSEEK_API_KEY` | 板块5必需 | DeepSeek API Key，仅用于跨板块科研启发 |
| `NCBI_API_KEY` | 否 | 提高 PubMed E-utilities 速率 |
| `S3_BUCKET_NAME` | R2 时必需 | 建议 `research-radar-data` |
| `S3_ACCESS_KEY_ID` | R2 时必需 | R2 Token Access Key |
| `S3_SECRET_ACCESS_KEY` | R2 时必需 | R2 Token Secret |
| `S3_ENDPOINT_URL` | R2 时必需 | `https://<account>.r2.cloudflarestorage.com` |
| `S3_REGION` | 否 | Cloudflare R2 使用 `auto` |
| `EMAIL_FROM` | 邮件时必需 | SMTP 发件邮箱 |
| `EMAIL_PASSWORD` | 邮件时必需 | SMTP 授权码 |
| `EMAIL_TO` | 邮件时必需 | `zrxzrx1227@163.com` |
| `EMAIL_SMTP_SERVER` | 否 | 163 邮箱默认自动识别 |
| `EMAIL_SMTP_PORT` | 否 | 默认 465 |

Secrets 不得写入配置文件、报告或 manifest。

## DeepSeek

1. 在 DeepSeek 开放平台创建 API Key。
2. 仓库 **Settings → Secrets and variables → Actions → New repository secret**。
3. 名称必须填写 `DEEPSEEK_API_KEY`，值粘贴 API Key。
4. 项目默认使用 `deepseek-v4-flash` 非思考模式和 JSON Output，以控制费用并稳定解析。

板块5只向模型发送板块1–4已经公开展示的标题、短摘要、标签和来源标识，不发送
R2密钥、邮箱密码或其他 Secrets。AI请求与响应会去除认证信息后归档到R2，manifest
仅保存模型、提示词版本、输入哈希、条目数和token用量。模型不可用时，前四板块、
邮件和Pages仍会正常生成。

## Pages

仓库 Settings → Pages → Build and deployment → Source 选择 **GitHub Actions**。
工作流使用官方 `configure-pages`、`upload-pages-artifact` 和 `deploy-pages`。

## SCImago

1. 打开 [SCImago Medicine 排名页](https://www.scimagojr.com/journalrank.php?area=2700)，
   选择网站提供的最新年份并下载 CSV。
2. 将原始文件放到本地 `incoming/`（该目录已被 Git 忽略，不会误传到公开仓库）。
3. 直接导入，无需手工筛选或修改列名：

   ```bash
   python -m research_radar import-scimago incoming/scimagojr.csv
   ```

   若文件没有年份列且文件名也不含年份，增加 `--year 2025`。
4. 运行 `python -m research_radar doctor`，确认 `scimago_q1_issns` 大于 0。

导入器会自动筛选 `SJR Best Quartile == Q1`、只保留 Medicine、规范化 ISSN，
并把来源文件名、年份、SHA-256、期刊数和 ISSN 数写入
`reference/scimago_metadata.json`。公开仓库仅保存派生清单和追溯元数据；
原始官方 CSV 不提交 Git。

> SCImago Q1 是本项目首版的可公开复核替代口径，不等同于 JCR Q1。

## OpenAlex

1. 登录 [OpenAlex API 设置页](https://openalex.org/settings/api)并创建免费 API Key。
2. 仓库 **Settings → Secrets and variables → Actions → New repository secret**。
3. 名称必须填写 `OPENALEX_API_KEY`，值粘贴刚创建的 Key。
4. 不要把 Key 写入代码、CSV、Issue、日志或聊天消息。

OpenAlex 当前为 API Key 提供每日免费额度；项目使用它补充主题与引用指标。
未配置时周报仍可生成，但板块 1 的热点评分会缺少 OpenAlex 增强信息。
