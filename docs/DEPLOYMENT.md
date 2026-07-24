# 部署说明

## GitHub Secrets

| Secret | 必需 | 用途 |
|---|---:|---|
| `OPENALEX_API_KEY` | 建议 | OpenAlex 免费 API Key |
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

## Pages

仓库 Settings → Pages → Build and deployment → Source 选择 **GitHub Actions**。
工作流使用官方 `configure-pages`、`upload-pages-artifact` 和 `deploy-pages`。

## SCImago

从 SCImago Journal & Country Rank 下载最新版 Medicine 数据，筛选 `SJR Best
Quartile == Q1`，按 `reference/scimago_q1_medicine.csv` 的表头保存。运行
`python -m research_radar doctor` 检查。原始下载文件宜保存在 R2，仓库只
保存导入清单及 `reference/scimago_metadata.json` 的来源与 SHA-256。

