# SounderOne 多平台智能客服 Agent

这是一个可运行的首期客服 Agent 后端。项目已将问卷中的业务边界落实为程序规则：AI 不执行退款、补发或修改订单；不良反应、复杂售后、强烈情绪、法律/舆情、敏感个人信息及知识不足场景自动转人工；非工作时间采取更严格的回答阈值。

当前知识库是明确标记的测试数据，不能用于生产客服。淘宝、抖音、京东、拼多多、小红书、微信小店、快手、蘑菇街、得物均已有统一接入入口；各平台真实验签、消息字段和发消息 API 需要开放平台应用、权限和官方回调样例后实现。

## 技术栈

- Python 3.11+、FastAPI、Pydantic
- OpenAI Responses API（可选）；默认 Mock 模式无需密钥
- 本地 JSON 检索用于开发；生产目标为 PostgreSQL + pgvector
- 进程内会话存储用于开发；生产目标为 PostgreSQL，Redis 用于幂等、限流和异步任务
- pytest、Docker、GitHub Actions（待绑定远程仓库后启用仓库规则）

架构和演进说明见 [docs/architecture.md](docs/architecture.md)，平台接入清单见 [docs/platform_integration.md](docs/platform_integration.md)。

## 本地运行

```bash
cp .env.example .env
uv venv --python /Users/ao/anaconda3/bin/python
uv sync --extra dev
uv run uvicorn app.main:app --reload
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

## 替换正式知识库

正式资料到位后，先转换成 UTF-8 JSON 数组，每项包含 `id`、`title`、`content`、`tags`，替换 `KNOWLEDGE_PATH` 指向的文件，再调用重载接口。上线前必须由业务负责人抽查并运行回归问题集；不要直接把问卷里的“已发送”当作有效知识。

## 测试

```bash
uv run pytest
```
