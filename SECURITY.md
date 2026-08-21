# 安全说明

本文件描述 DocRAG 的安全边界与漏洞报告方式。自托管单机部署请先阅读 [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) 与 [docs/MATURITY_MATRIX.md](docs/MATURITY_MATRIX.md)。

## 信任模型（已知边界）

- **身份**：后端仅在 `RAG_TRUSTED_PROXY=true` 时信任反向代理注入的 `X-Rag-Tenant / X-Rag-User / X-Rag-Group` 头；CORS 不允许浏览器直接发送这些头，可信反代需自行以 `proxy_set_header` 覆盖客户端同名头。**请勿把后端 8000 端口直接暴露到不可信网络**——绕过可信代理等于绕过身份注入。
- **多租户**：ACL 按租户/属主/组过滤（列表/详情/文件/检索/追踪均 fail-closed），但真实 OIDC/SSO 登录、密钥轮换、保留期与 PII 策略属于产品决策（见 MATURITY_MATRIX）。
- **模型 API Key**：设置页保存的 key 明文存储于本地 SQLite（`runtime_config` 表），API 响应只回传 `api_key_set` 布尔、不回显明文；该设计面向单机自托管，多租户产品化时必须改为加密存储或外部密钥管理。
- **查询隐私**：用户 query 原文与可反查哈希不落库（`trace.query_hash` 固定为 `not_stored`）。
- **LLM 越权（OWASP LLM06）**：生成内容先缓冲并校验引用，无有效引用的内容不泄出；权限判定一律由服务端按已认证身份执行，模型不裁决权限。

## 报告漏洞

请勿在公开渠道提交漏洞细节。联系仓库所有者（GitHub: `moonbrigt`）并说明：

1. 影响组件与版本（`git rev-parse HEAD`）
2. 复现步骤（最小化）
3. 期望行为与实际行为

## 已知未覆盖

- 真实模型权重链路的供应链校验（Docling/bge 权重下载为运行期行为，未做签名固定）
- 上传文件格式的深度校验（当前按扩展名与解析结果判定）
- 速率限制与暴力破解防护（无登录体系，依赖部署层网关）
