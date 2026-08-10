# 技术架构与决策

## 当前范围

项目只解决抖音文字客服的产品知识问答。模拟器用于无平台凭证时的端到端测试。其他平台、订单工具、自动退款/补发、图像/语音和多 Agent 不在本期范围。

## LangGraph

```text
START
  -> safety_guard
       | risk -> handoff -> END
  -> understand_query
  -> hybrid_retrieve
  -> relevance_gate
       | low confidence -> handoff -> END
  -> generate_answer
  -> output_guard
       | forbidden claim -> handoff -> END
  -> finalize_response
  -> END
```

- `safety_guard`：确定性检测不良反应、孕期、医美、复杂售后、法律/舆情和 PII。
- `understand_query`：恢复“这个/这款”指代的上一产品，生成检索查询。
- `hybrid_retrieve`：同时执行 Dense 和 BM25，使用 RRF 合并名次。
- `relevance_gate`：应用置信度、工作时间、产品浓度和查询意图门槛。
- `generate_answer`：Mock 或 OpenAI Responses API 只使用召回文档组织答案。
- `output_guard`：拦截医疗、绝对化功效和未授权承诺。
- `finalize_response`：返回引用、检索通道和完整节点轨迹。

开发期使用 LangGraph `InMemorySaver`。它支持单进程多轮上下文，但重启后丢失；抖音灰度上线前替换为 Postgres Checkpointer。

## 混合 RAG

`knowledge/sounderone_knowledge.json` 是审核后的知识源，Qdrant 是运行时索引。每个 active 文档同时写入：

1. `dense`：语义向量。开发/测试使用可复现 hash embedding，生产使用 OpenAI embedding。
2. `bm25`：基于词频、文档长度和语料 IDF 生成的稀疏向量。

查询时两个通道各召回 Top 50，用 RRF 融合，再结合 IDF 查询覆盖率排序。查询中的英文/数字词元（如 VCIP、5、10）必须出现在候选文档中；“用法/搭配/对比”只在对应知识类别中排序。

Qdrant 只写入 210 条 `active` 文档。`review_required` 和 `handoff_only` 从运行索引中物理排除。

## 运行边界

- FastAPI 负责 HTTP、共享密钥、载荷校验和管理接口。
- `/tester` 是内置的本地测试窗口，只调用 `simulator` API，可视化引用、检索通道和 Graph 轨迹；它不是生产坐席系统。
- `DouyinAdapter` 目前是归一化联调契约，不声称已完成官方验签和发信。
- `(platform, message_id)` 负责单进程幂等。
- 审计记录写入前脱敏手机号和身份证号。
- Agent 无订单写权限，不执行退款、补发或修改地址。

## 上线前必须完成

1. 抖音官方验签、解密、token、发信、限流和重试。
2. 将 LangGraph checkpoint、幂等和审计记录持久化。
3. 使用真实客服问题调整 embedding、RRF、Top-K 和置信度。
4. 完成 46 个知识冲突的业务/合规审核。
5. 连接真实人工队列，并验证转接 SLA。
