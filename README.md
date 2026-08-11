# SOUNDERONE 抖音智能客服 Agent

这是一个聚焦抖音单平台的客服 Agent MVP。LangGraph 负责有状态工作流，Qdrant 同时执行 Dense Vector 和 BM25 检索，再使用 RRF 融合。高风险、知识不足和生成违规内容会绕过自动回答并转人工。

当前只接受 `douyin` 和本地 `simulator`，已删除其他电商平台的预留代码。抖音正式验签、解密和发送 API 需要应用凭证与官方回调样例后完成。

## 工作流

```text
START
  -> safety_guard
       | high risk -> handoff
  -> intent_router
       | pure greeting -> smalltalk_response
       | out of scope -> out_of_scope_response
       | missing product/context -> clarify_response
  -> rewrite_query
  -> route_knowledge (product / faq)
  -> hybrid_retrieve
  -> relevance_gate
       | no reliable hit -> handoff
  -> generate_answer
       | insufficient context / model error -> handoff
  -> output_guard
  -> finalize_response
  -> END
```

无关问题由20条已审核的 SOUNDERONE 能力范围话术稳定随机回复；缺少产品名的问题单独追问。两类响应均不查询知识库。命中后由 DeepSeek V4 Flash（或 Mock/OpenAI）严格依据检索片段，以官方客服身份直接回答；输出不得出现“根据现有资料”“知识库里提到”等内部来源措辞。知识不足、模型不可用或输出违规都会转人工。

“有什么美白产品推荐”这类选品问题不要求用户先提供产品名，会进入 `recommendation` 意图并检索产品库与 FAQ。推荐候选必须匹配美白、保湿、控油等明确需求词；对应需求没有可靠知识时直接转人工。

## 技术栈

- Python 3.11+、FastAPI、Pydantic
- LangGraph `StateGraph` 和开发期 `InMemorySaver`
- Qdrant Dense Vector + BM25 Sparse Vector
- Reciprocal Rank Fusion（RRF）
- DeepSeek V4 Flash 官方 OpenAI 兼容 API（生产回答，可配置）
- OpenAI Responses API（可选替代）
- OpenAI Embeddings（生产可选）；默认 hash embedding 只用于离线开发和测试
- Excel 确定性清洗、冲突检测和风险分区

架构详情见 [docs/architecture.md](docs/architecture.md)，抖音接入边界见 [docs/douyin_integration.md](docs/douyin_integration.md)，知识审计见 [docs/knowledge_base_analysis.md](docs/knowledge_base_analysis.md)。

## 本地运行

```bash
cp .env.example .env
UV_CACHE_DIR=/tmp/sounderone-uv-cache UV_PROJECT_ENVIRONMENT=.venv.nosync uv sync --extra dev
UV_CACHE_DIR=/tmp/sounderone-uv-cache UV_PROJECT_ENVIRONMENT=.venv.nosync uv run uvicorn app.main:app --reload
```

默认使用内存 Qdrant、hash embedding 和 Mock LLM，无需密钥。接入 DeepSeek V4 Flash 时设置：

```dotenv
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=...
DEEPSEEK_MODEL=deepseek-v4-flash
EMBEDDING_PROVIDER=openai
OPENAI_API_KEY=...
QDRANT_URL=http://qdrant:6333
```

`deepseek-v4-flash` 使用 DeepSeek 官方 OpenAI 兼容地址 `https://api.deepseek.com`；模型名与接口以 [DeepSeek Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing) 为准。

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

第一条命令生成完整审计源、冲突报告以及运行时使用的两个文件：

- `knowledge/product_knowledge.json`：64 条产品知识。
- `knowledge/customer_faq.json`：223 条历史 FAQ。

第二条命令把两个文件中的 210 条 `active` 知识建立为 Dense + BM25 双索引。

## 测试

```bash
UV_CACHE_DIR=/tmp/sounderone-uv-cache UV_PROJECT_ENVIRONMENT=.venv.nosync uv run pytest -q -p no:cacheprovider
```

原始知识中 39 条 `review_required` 和 38 条 `handoff_only` 不会进入 Qdrant 自动回答索引。
