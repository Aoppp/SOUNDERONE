# 技术架构与决策

## 当前范围

项目只解决抖音文字客服的产品知识问答。模拟器用于无平台凭证时的端到端测试。其他平台、订单工具、自动退款/补发、图像/语音和多 Agent 不在本期范围。

## LangGraph

```text
START
  -> safety_guard
       | risk / user requests human -> handoff -> END
  -> intent_router
       | pure greeting -> smalltalk_response -> output_guard
       | out of scope -> out_of_scope_response -> output_guard
       | missing product/context -> clarify_response -> output_guard
  -> rewrite_query
  -> route_knowledge
  -> hybrid_retrieve
  -> relevance_gate
       | low confidence -> handoff -> END
       | reliable FAQ -> direct_faq_answer -> output_guard
       | reliable product knowledge -> generate_answer
       | insufficient knowledge / unavailable -> handoff -> END
  -> output_guard
       | forbidden claim -> handoff -> END
  -> finalize_response
  -> END
```

- `safety_guard`：确定性检测不良反应、孕期、医美、复杂售后、法律/舆情和 PII；“转人工/人工服务/不要机器人”等用户主动请求也在此直接转接。
- `intent_router`：区分纯问候、范围外问题、缺少产品上下文的问题和可检索问题；高危检测已经在它之前完成。路由前会对 active FAQ 做一次高置信度预识别（当前门槛 `0.90`），避免“容量/没装满”等未列入手工业务关键词的现有 FAQ 在 RAG 前被误判为范围外。
- `smalltalk_response`：对“你好/在吗/hello”等纯问候返回固定欢迎语，不查询 RAG，避免把寒暄误匹配为产品知识。
- `out_of_scope_response`：从20条 SOUNDERONE 范围说明中按会话ID和消息ID稳定选择一条；重试结果一致，不调用 RAG。
- `clarify_response`：对“怎么用”“这个适合我吗”等缺产品或缺上下文问题追问产品名，不调用 RAG。
- `rewrite_query`：只使用原消息和 LangGraph 已保存的产品上下文补全独立查询，不调用模型、不创造产品、浓度或肤质。
- `route_knowledge`：高置信度预识别的 FAQ 只查 FAQ 库；物流、发票、促销等也只查 FAQ；其他产品问题同时查询产品知识和 FAQ。
- `recommendation`：允许没有具体产品名的选品问题进入产品库和 FAQ，并在多轮中继承上一轮推荐意图。先识别美白/提亮、毛孔、控油、祛痘、抗衰/抗皱/淡纹/紧致、保湿、黑头、眼袋、敏感和去屑等同义目标；产品介绍可按同组词匹配，FAQ 还必须包含用户本轮说出的目标词，避免相近但不相干的话术进入上下文。没有目标或没有对应知识时直接转人工。
- `hybrid_retrieve`：同时执行 Dense 和 BM25，使用 RRF 合并名次。
- `relevance_gate`：应用置信度、工作时间、产品浓度和查询意图门槛。排名第一的可靠命中属于 FAQ 时，不再受夜间生成缩权影响。
- `direct_faq_answer`：对已通过置信度门槛的 active FAQ 直接返回排名第一的标准答案，不调用 DeepSeek；只保留该条 FAQ 引用并继续执行输出清理。
- `generate_answer`：默认 Mock；生产可配置 DeepSeek V4 Flash，亦保留 OpenAI 替代。模型只组织检索片段，返回 `INSUFFICIENT_KNOWLEDGE` 或调用失败时转人工。
- `output_guard`：拦截医疗、绝对化功效和未授权承诺，并确定性清理“根据现有资料/知识库提到/目前资料里”等第三方转述措辞。
- `finalize_response`：返回引用、检索通道和完整节点轨迹。

开发期使用 LangGraph `InMemorySaver`。它支持单进程多轮上下文，但重启后丢失；抖音灰度上线前替换为 Postgres Checkpointer。

## 混合 RAG

`knowledge/sounderone_knowledge.json` 保留为完整审计源，运行时读取 `product_knowledge.json` 和 `customer_faq.json`。两文件保持原文档 ID、安全状态和 Excel 溯源；Qdrant 使用同一个 Collection，通过 `knowledge_type=product|faq` 路由。每个 active 文档同时写入：

1. `dense`：语义向量。开发/测试使用可复现 hash embedding，生产使用 OpenAI embedding。
2. `bm25`：基于词频、文档长度和语料 IDF 生成的稀疏向量。

查询时两个通道各召回 Top 50，用 RRF 融合，再结合 IDF 查询覆盖率排序。查询中的英文/数字词元（如 VCIP、5、10）必须出现在候选文档中；中文候选必须与查询共享至少一个多字词，不能仅凭“他/好”等单字碰撞通过。用法、搭配、对比、物流、发票和促销意图只允许匹配相应知识类别及标题标签。`relevance_gate` 只把超过最低分且与 Top1 分差不超过配置窗口的候选交给生成模型，低分次级结果不会污染上下文。若正式库没有物流答案，“多久发货”会转人工，不能误匹配“多久有效果”。

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
