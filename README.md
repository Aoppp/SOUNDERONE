# SounderOne 多平台智能客服 Agent

这是一个可运行的首期客服 Agent 后端。项目已将问卷中的业务边界落实为程序规则：AI 不执行退款、补发或修改订单；不良反应、复杂售后、强烈情绪、法律/舆情、敏感个人信息及知识不足场景自动转人工；非工作时间采取更严格的回答阈值。

当前已经由 `产品话术汇总完整版本.xlsx` 构建出可追溯的正式知识库候选集。系统只自动检索审核规则允许的条目；冲突、孕期/医美、不良反应和复杂售后内容不会作为自动回答依据。淘宝、抖音、京东、拼多多、小红书、微信小店、快手、蘑菇街、得物均已有统一接入入口；各平台真实验签、消息字段和发消息 API 仍需要开放平台应用、权限和官方回调样例。

## 技术栈

- Python 3.11+、FastAPI、Pydantic
- OpenAI Responses API（可选）；默认 Mock 模式无需密钥
- Excel 确定性导入、IDF 加权中文词法检索；生产目标为 BM25 + PostgreSQL/pgvector 混合检索
- 进程内会话存储用于开发；生产目标为 PostgreSQL，Redis 用于幂等、限流和异步任务
- pytest、Docker、GitHub Actions（待绑定远程仓库后启用仓库规则）

架构和演进说明见 [docs/architecture.md](docs/architecture.md)，知识审计见 [docs/knowledge_base_analysis.md](docs/knowledge_base_analysis.md)，平台接入清单见 [docs/platform_integration.md](docs/platform_integration.md)。

## 本地运行

```bash
cp .env.example .env
UV_PROJECT_ENVIRONMENT=.venv.nosync uv venv --python /Users/ao/anaconda3/bin/python
UV_PROJECT_ENVIRONMENT=.venv.nosync uv sync --extra dev
UV_PROJECT_ENVIRONMENT=.venv.nosync uv run uvicorn app.main:app --reload
```

服务启动后：

- 健康检查：`GET http://127.0.0.1:8000/health`
- OpenAPI：`http://127.0.0.1:8000/docs`
- 模拟消息：`POST /v1/webhooks/simulator`
- 重载知识库：`POST /v1/admin/knowledge/reload`
- 会话审计：`GET /v1/conversations/{conversation_id}`

管理接口需传 `X-Admin-Key`；生产环境必须替换示例密钥。平台会以 `(platform, message_id)` 幂等处理重复事件，审计记录会自动遮盖手机号和身份证号。

模拟请求：

```bash
curl -X POST http://127.0.0.1:8000/v1/webhooks/simulator \
  -H 'Content-Type: application/json' \
  -H 'X-Webhook-Secret: change-me' \
  -d '{"message_id":"m1","conversation_id":"c1","user_id":"u1","text":"多久发货？"}'
```

## 使用 OpenAI

在 `.env` 中设置 `LLM_PROVIDER=openai`、`OPENAI_API_KEY` 和可用的 `OPENAI_MODEL`。模型只负责在召回资料的范围内组织语言；转人工和合规判断位于模型调用前后，不依赖提示词自觉。

## 重建知识库

原始工作簿含订单明细，因此被明确排除在 Git 之外。更新本地 Excel 后运行：

```bash
UV_PROJECT_ENVIRONMENT=.venv.nosync uv run python scripts/build_knowledge.py \
  '产品话术汇总完整版本.xlsx'
```

构建器会生成：

- `knowledge/sounderone_knowledge.json`：Agent 使用的知识条目。
- `knowledge/build_report.json`：工作表决策、条目状态、风险标签和冲突报告。

不要直接编辑生成 JSON。应修改来源 Excel，重新构建并检查报告，然后调用 `POST /v1/admin/knowledge/reload`。当前从 291 条原始候选合并 4 条重复内容后得到 287 条：210 条 active、39 条 review-required、38 条 handoff-only。只有 active 条目参与自动检索。

## 测试

```bash
UV_PROJECT_ENVIRONMENT=.venv.nosync uv run pytest
```

项目放在 iCloud Desktop 下时必须保留 `UV_PROJECT_ENVIRONMENT=.venv.nosync`，避免虚拟环境被自动卸载为 `dataless`。
