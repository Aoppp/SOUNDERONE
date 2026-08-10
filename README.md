# SounderOne 抖音智能客服 Agent

这是一个聚焦抖音单平台的客服 Agent MVP。LangGraph 负责有状态工作流，Qdrant 同时执行 Dense Vector 和 BM25 检索，再使用 RRF 融合。高风险、知识不足和生成违规内容会绕过自动回答并转人工。

当前只接受 `douyin` 和本地 `simulator`，已删除其他电商平台的预留代码。抖音正式验签、解密和发送 API 需要应用凭证与官方回调样例后完成。

## 工作流

```text
START
  -> safety_guard
  -> understand_query
       | pure greeting -> smalltalk_response
  -> hybrid_retrieve
  -> relevance_gate
  -> generate_answer
  -> output_guard
  -> finalize_response
  -> END
```

`safety_guard`、`relevance_gate` 和 `output_guard` 都可以分支到 `handoff`。每次回复会返回 `graph_trace`、知识引用以及命中的 `dense` / `bm25` 检索通道。

## 技术栈

- Python 3.11+、FastAPI、Pydantic
- LangGraph `StateGraph` 和开发期 `InMemorySaver`
- Qdrant Dense Vector + BM25 Sparse Vector
- Reciprocal Rank Fusion（RRF）
- OpenAI Responses API（可选）
- OpenAI Embeddings（生产可选）；默认 hash embedding 只用于离线开发和测试
- Excel 确定性清洗、冲突检测和风险分区

架构详情见 [docs/architecture.md](docs/architecture.md)，抖音接入边界见 [docs/douyin_integration.md](docs/douyin_integration.md)，知识审计见 [docs/knowledge_base_analysis.md](docs/knowledge_base_analysis.md)。

## 本地运行

```bash
cp .env.example .env
UV_CACHE_DIR=/tmp/sounderone-uv-cache UV_PROJECT_ENVIRONMENT=.venv.nosync uv sync --extra dev
UV_CACHE_DIR=/tmp/sounderone-uv-cache UV_PROJECT_ENVIRONMENT=.venv.nosync uv run uvicorn app.main:app --reload
```

默认使用内存 Qdrant、hash embedding 和 Mock LLM，无需密钥。生产向量需设置：

```dotenv
LLM_PROVIDER=openai
EMBEDDING_PROVIDER=openai
OPENAI_API_KEY=...
QDRANT_URL=http://qdrant:6333
```

### 浏览器测试窗口

服务启动后直接打开：

```text
http://127.0.0.1:8000/tester
```

页面可以连续发送多轮消息，并展示：

- 回答/转人工状态与原因。
- Excel 工作表、行号和知识分类。
- Dense / BM25 检索通道与融合分数。
- LangGraph 实际经过的节点轨迹。
- 正常问答、产品对比、风险转人工和未知问题快捷场景。

默认 Webhook Secret 是 `change-me`；如果 `.env` 已修改，在页面左侧填入相同值。点击“新建会话”会更换会话 ID 并清空当前界面。

模拟请求：

```bash
curl -X POST http://127.0.0.1:8000/v1/webhooks/simulator \
  -H 'Content-Type: application/json' \
  -H 'X-Webhook-Secret: change-me' \
  -d '{"message_id":"m1","conversation_id":"c1","user_id":"u1","text":"5%传明酸怎么使用？"}'
```

常用接口：

- `GET /health`
- `POST /v1/webhooks/douyin`
- `POST /v1/webhooks/simulator`
- `POST /v1/admin/knowledge/reload`
- `GET /v1/conversations/{conversation_id}`

## 知识库更新

原始 Excel 含订单数据，已被 Git 忽略。更新流程：

```bash
UV_PROJECT_ENVIRONMENT=.venv.nosync uv run python scripts/build_knowledge.py '产品话术汇总完整版本.xlsx'
UV_PROJECT_ENVIRONMENT=.venv.nosync uv run python scripts/index_knowledge.py
```

第一条命令生成脱敏 JSON 和冲突报告；第二条命令将 210 条 `active` 知识建立为 Dense + BM25 双索引。

## 测试

```bash
UV_CACHE_DIR=/tmp/sounderone-uv-cache UV_PROJECT_ENVIRONMENT=.venv.nosync uv run pytest -q -p no:cacheprovider
```

原始知识中 39 条 `review_required` 和 38 条 `handoff_only` 不会进入 Qdrant 自动回答索引。
