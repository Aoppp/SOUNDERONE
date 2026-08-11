from __future__ import annotations

import re

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from app.agent.state import AgentState
from app.agent.responses import stable_out_of_scope_response
from app.config import Settings
from app.llm import LanguageModel
from app.models import AgentReply, ConversationEvent, Decision, IncomingMessage
from app.policy import SafetyPolicy
from app.rag import HybridKnowledgeBase, recommendation_goals
from app.store import InMemoryConversationStore


class SounderOneGraphAgent:
    """Small, deterministic LangGraph workflow for product-support RAG."""

    SUPPORT_CUES = (
        "产品",
        "精华",
        "面霜",
        "乳霜",
        "眼霜",
        "洗发水",
        "护发素",
        "头皮",
        "护肤",
        "成分",
        "浓度",
        "功效",
        "效果",
        "用法",
        "使用",
        "怎么用",
        "搭配",
        "叠加",
        "区别",
        "推荐",
        "哪款",
        "选择",
        "适合",
        "肤质",
        "敏感肌",
        "油皮",
        "干皮",
        "痘",
        "斑",
        "泛红",
        "搓泥",
        "结晶",
        "质地",
        "气味",
        "味道",
        "包装",
        "瓶子",
        "保质期",
        "生产日期",
        "发货",
        "物流",
        "快递",
        "订单",
        "价格",
        "活动",
        "赠品",
        "发票",
        "退款",
        "退货",
        "补发",
        "漏发",
        "少发",
        "破损",
        "售后",
        "投诉",
    )

    # These intents can be answered without a product name. Product-specific
    # questions such as "怎么用" or "效果怎么样" require an explicit product
    # or a product carried over from the conversation.
    STANDALONE_SERVICE_CUES = (
        "发货",
        "物流",
        "快递",
        "配送",
        "到货",
        "订单",
        "价格",
        "多少钱",
        "优惠",
        "活动",
        "折扣",
        "到手价",
        "赠品",
        "发票",
        "退款",
        "退货",
        "补发",
        "漏发",
        "少发",
        "破损",
        "售后",
        "投诉",
    )

    RECOMMENDATION_CUES = ("推荐", "哪款", "选什么", "有什么产品", "产品选择")

    def __init__(
        self,
        settings: Settings,
        knowledge: HybridKnowledgeBase,
        policy: SafetyPolicy,
        llm: LanguageModel,
        store: InMemoryConversationStore,
    ):
        self.settings = settings
        self.knowledge = knowledge
        self.policy = policy
        self.llm = llm
        self.store = store
        self.checkpointer = InMemorySaver()
        self.graph = self._build_graph()

    @staticmethod
    def _step(state: AgentState, node: str) -> list[str]:
        return [*state.get("trace", []), node]

    @staticmethod
    def _message(state: AgentState) -> IncomingMessage:
        return IncomingMessage.model_validate(state["message"])

    def _build_graph(self):
        builder = StateGraph(AgentState)
        builder.add_node("safety_guard", self._safety_guard)
        builder.add_node("intent_router", self._intent_router)
        builder.add_node("smalltalk_response", self._smalltalk_response)
        builder.add_node("out_of_scope_response", self._out_of_scope_response)
        builder.add_node("clarify_response", self._clarify_response)
        builder.add_node("rewrite_query", self._rewrite_query)
        builder.add_node("route_knowledge", self._route_knowledge)
        builder.add_node("hybrid_retrieve", self._hybrid_retrieve)
        builder.add_node("relevance_gate", self._relevance_gate)
        builder.add_node("direct_faq_answer", self._direct_faq_answer)
        builder.add_node("generate_answer", self._generate_answer)
        builder.add_node("output_guard", self._output_guard)
        builder.add_node("finalize_response", self._finalize_response)
        builder.add_node("handoff", self._handoff)

        builder.add_edge(START, "safety_guard")
        builder.add_conditional_edges(
            "safety_guard",
            self._route_after_safety,
            {"continue": "intent_router", "handoff": "handoff"},
        )
        builder.add_conditional_edges(
            "intent_router",
            self._route_after_intent,
            {
                "smalltalk": "smalltalk_response",
                "out_of_scope": "out_of_scope_response",
                "clarify": "clarify_response",
                "rewrite": "rewrite_query",
            },
        )
        builder.add_edge("smalltalk_response", "output_guard")
        builder.add_edge("out_of_scope_response", "output_guard")
        builder.add_edge("clarify_response", "output_guard")
        builder.add_edge("rewrite_query", "route_knowledge")
        builder.add_edge("route_knowledge", "hybrid_retrieve")
        builder.add_edge("hybrid_retrieve", "relevance_gate")
        builder.add_conditional_edges(
            "relevance_gate",
            self._route_after_relevance,
            {
                "faq": "direct_faq_answer",
                "generate": "generate_answer",
                "handoff": "handoff",
            },
        )
        builder.add_edge("direct_faq_answer", "output_guard")
        builder.add_conditional_edges(
            "generate_answer",
            self._route_after_generation,
            {"respond": "output_guard", "handoff": "handoff"},
        )
        builder.add_conditional_edges(
            "output_guard",
            self._route_after_output,
            {"respond": "finalize_response", "handoff": "handoff"},
        )
        builder.add_edge("finalize_response", END)
        builder.add_edge("handoff", END)
        return builder.compile(checkpointer=self.checkpointer)

    def _safety_guard(self, state: AgentState) -> dict:
        risk = self.policy.evaluate_incoming(self._message(state).text)
        risk_data = {
            "must_handoff": risk.must_handoff,
            "reason": risk.reason,
            "risk_tags": risk.risk_tags,
        }
        update: dict = {"risk": risk_data, "trace": self._step(state, "safety_guard")}
        if risk.must_handoff:
            update.update(handoff_reason=risk.reason or "安全规则要求转人工", risk_tags=risk.risk_tags)
        return update

    @staticmethod
    def _route_after_safety(state: AgentState) -> str:
        return "handoff" if state["risk"]["must_handoff"] else "continue"

    def _intent_router(self, state: AgentState) -> dict:
        text = self._message(state).text
        normalized = re.sub(r"[\s，。！？!?~～,.]+", "", text.lower())
        greetings = {
            "你好",
            "你好呀",
            "你好啊",
            "您好",
            "您好呀",
            "嗨",
            "哈喽",
            "hello",
            "hi",
            "在吗",
            "在不在",
            "早上好",
            "下午好",
            "晚上好",
        }
        if normalized in greetings:
            return {
                "conversation_intent": "smalltalk",
                "retrieval_query": "",
                "trace": self._step(state, "intent_router"),
            }
        explicit_product = self.knowledge.identify_product(text)
        last_product = explicit_product or state.get("last_product", "")
        refers_to_context = any(word in text for word in ("这个", "它", "这款", "刚才那个"))
        has_supported_cue = any(cue in text for cue in self.SUPPORT_CUES)
        has_standalone_service_cue = any(cue in text for cue in self.STANDALONE_SERVICE_CUES)
        has_recommendation_goal = bool(recommendation_goals(text))
        continues_recommendation = (
            state.get("query_intent") == "recommendation" and has_recommendation_goal
        )
        has_recommendation_cue = (
            any(cue in text for cue in self.RECOMMENDATION_CUES)
            or continues_recommendation
            or (
                has_recommendation_goal
                and bool(re.search(r"有没有|有什么|什么|哪|呢", text))
            )
        )
        mentions_brand = bool(
            re.search(r"sounder\s*one|搜得旺|你们(?:家)?品牌|你家品牌", text, re.IGNORECASE)
        )
        if refers_to_context and not last_product:
            return {
                "conversation_intent": "clarification",
                "retrieval_query": "",
                "trace": self._step(state, "intent_router"),
            }
        if (
            not explicit_product
            and not last_product
            and has_supported_cue
            and not has_standalone_service_cue
            and not has_recommendation_cue
        ):
            return {
                "conversation_intent": "clarification",
                "retrieval_query": "",
                "trace": self._step(state, "intent_router"),
            }
        is_knowledge_query = bool(
            explicit_product
            or (last_product and has_supported_cue)
            or has_standalone_service_cue
            or has_recommendation_cue
            or mentions_brand
        )
        if not is_knowledge_query:
            return {
                "conversation_intent": "out_of_scope",
                "retrieval_query": "",
                "trace": self._step(state, "intent_router"),
            }
        return {
            "conversation_intent": "knowledge_query",
            "explicit_product": explicit_product,
            "last_product": last_product,
            "trace": self._step(state, "intent_router"),
        }

    @staticmethod
    def _route_after_intent(state: AgentState) -> str:
        intent = state.get("conversation_intent")
        if intent == "smalltalk":
            return "smalltalk"
        if intent == "out_of_scope":
            return "out_of_scope"
        if intent == "clarification":
            return "clarify"
        return "rewrite"

    def _smalltalk_response(self, state: AgentState) -> dict:
        return {
            "generated_text": (
                "宝宝你好～我是 SOUNDERONE 智能客服。"
                "你可以直接问我产品用法、成分搭配或其他售前问题。"
            ),
            "hits": [],
            "trace": self._step(state, "smalltalk_response"),
        }

    def _out_of_scope_response(self, state: AgentState) -> dict:
        message = self._message(state)
        return {
            "generated_text": stable_out_of_scope_response(
                message.external_conversation_id,
                message.external_message_id,
            ),
            "hits": [],
            "response_decision": Decision.safe_fallback.value,
            "trace": self._step(state, "out_of_scope_response"),
        }

    def _clarify_response(self, state: AgentState) -> dict:
        return {
            "generated_text": (
                "宝宝，我还没理解你想咨询的具体问题～"
                "可以告诉我产品名称，以及你想了解用法、成分搭配还是售后问题。"
            ),
            "hits": [],
            "response_decision": Decision.safe_fallback.value,
            "trace": self._step(state, "clarify_response"),
        }

    def _rewrite_query(self, state: AgentState) -> dict:
        """Resolve conversation references without allowing the model to invent entities."""
        text = self._message(state).text
        explicit_product = state.get("explicit_product", "")
        resolved_product = explicit_product or state.get("last_product", "")
        retrieval_query = text
        if resolved_product and not explicit_product:
            retrieval_query = f"{resolved_product} {text}"
        return {
            "retrieval_query": retrieval_query,
            "last_product": resolved_product,
            "trace": self._step(state, "rewrite_query"),
        }

    def _route_knowledge(self, state: AgentState) -> dict:
        query = state["retrieval_query"]
        if re.search(r"发货|物流|快递|配送|到货", query):
            intent, knowledge_types = "shipping", ["faq"]
        elif "发票" in query:
            intent, knowledge_types = "invoice", ["faq"]
        elif re.search(r"价格|多少钱|优惠|活动|折扣|到手价", query):
            intent, knowledge_types = "promotion", ["faq"]
        elif re.search(r"退款|退货|补发|漏发|少发|破损|售后|投诉", query):
            intent, knowledge_types = "after_sales", ["faq"]
        elif re.search(r"推荐|哪款|选什么|有什么.*产品", query) or (
            recommendation_goals(query) and re.search(r"有没有|有什么|什么|哪|呢", query)
        ):
            intent, knowledge_types = "recommendation", ["product", "faq"]
        elif re.search(r"怎么使用|怎么用|如何用|怎样用|使用方法|使用顺序|用量", query):
            intent, knowledge_types = "usage", ["product", "faq"]
        elif re.search(r"搭配|叠加|一起用|能和|可以和|不能和|同用", query):
            intent, knowledge_types = "compatibility", ["product", "faq"]
        elif re.search(r"区别|对比|选哪个|怎么选", query):
            intent, knowledge_types = "comparison", ["product", "faq"]
        else:
            intent, knowledge_types = "product_information", ["product", "faq"]
        return {
            "query_intent": intent,
            "knowledge_types": knowledge_types,
            "trace": self._step(state, "route_knowledge"),
        }

    def _hybrid_retrieve(self, state: AgentState) -> dict:
        hits = self.knowledge.search(
            state["retrieval_query"],
            knowledge_types=set(state.get("knowledge_types", [])),
        )
        serialized = [
            {
                "document_id": hit.document.id,
                "score": hit.score,
                "retrieval_channels": list(hit.retrieval_channels),
            }
            for hit in hits
        ]
        return {"hits": serialized, "trace": self._step(state, "hybrid_retrieve")}

    def _relevance_gate(self, state: AgentState) -> dict:
        hits = state.get("hits", [])
        update: dict = {"trace": self._step(state, "relevance_gate")}
        if not hits or hits[0]["score"] < self.settings.knowledge_min_score:
            update["hits"] = []
            update.update(
                handoff_reason="知识库无可靠答案",
                risk_tags=["low_knowledge_confidence"],
            )
            return update

        top_score = hits[0]["score"]
        reliable_hits = [
            hit
            for hit in hits
            if hit["score"] >= self.settings.knowledge_min_score
            and top_score - hit["score"] <= self.settings.knowledge_score_window
        ]
        update["hits"] = reliable_hits
        restored_hits = self.knowledge.restore_hits(reliable_hits)
        direct_faq = bool(restored_hits and restored_hits[0].document.knowledge_type == "faq")
        update["direct_faq"] = direct_faq
        if not direct_faq and not self.policy.is_business_hours() and top_score < 0.62:
            update.update(
                handoff_reason="非工作时段且知识置信度不足",
                risk_tags=["off_hours_restricted"],
            )
        else:
            update.update(handoff_reason="", risk_tags=[])
        return update

    @staticmethod
    def _route_after_relevance(state: AgentState) -> str:
        if state.get("handoff_reason"):
            return "handoff"
        return "faq" if state.get("direct_faq") else "generate"

    def _direct_faq_answer(self, state: AgentState) -> dict:
        """Return an approved FAQ answer deterministically without invoking an LLM."""

        hits = state.get("hits", [])[:1]
        restored_hits = self.knowledge.restore_hits(hits)
        answer = restored_hits[0].document.content.strip()
        if not answer.startswith(("宝宝", "宝贝")):
            answer = f"宝宝，{answer}"
        return {
            "generated_text": answer,
            "hits": hits,
            "trace": self._step(state, "direct_faq_answer"),
        }

    async def _generate_answer(self, state: AgentState) -> dict:
        try:
            generated = await self.llm.answer(
                state["retrieval_query"],
                self.knowledge.restore_hits(state["hits"]),
            )
        except Exception:
            return {
                "generated_text": "",
                "handoff_reason": "回答模型暂时不可用",
                "risk_tags": ["generation_unavailable"],
                "trace": self._step(state, "generate_answer"),
            }
        update: dict = {
            "generated_text": generated,
            "trace": self._step(state, "generate_answer"),
        }
        if not generated or "INSUFFICIENT_KNOWLEDGE" in generated.upper():
            update.update(
                handoff_reason="知识片段不足以生成可靠答案",
                risk_tags=["generation_insufficient_knowledge"],
            )
        return update

    @staticmethod
    def _route_after_generation(state: AgentState) -> str:
        return "handoff" if state.get("handoff_reason") else "respond"

    def _output_guard(self, state: AgentState) -> dict:
        safe_text, forbidden = self.policy.sanitize_output(state["generated_text"])
        update: dict = {
            "generated_text": safe_text,
            "forbidden_claims": forbidden,
            "trace": self._step(state, "output_guard"),
        }
        if forbidden:
            update.update(
                handoff_reason="生成内容触发禁用词",
                risk_tags=[f"forbidden_claim:{word}" for word in forbidden],
            )
        return update

    @staticmethod
    def _route_after_output(state: AgentState) -> str:
        return "handoff" if state.get("forbidden_claims") else "respond"

    def _finalize_response(self, state: AgentState) -> dict:
        trace = self._step(state, "finalize_response")
        reply = AgentReply(
            conversation_id=self._message(state).external_conversation_id,
            decision=Decision(state.get("response_decision", Decision.answered.value)),
            text=state["generated_text"],
            citations=[hit.citation() for hit in self.knowledge.restore_hits(state["hits"])],
            graph_trace=trace,
        )
        return {"reply": reply.model_dump(mode="json"), "trace": trace}

    def _handoff(self, state: AgentState) -> dict:
        trace = self._step(state, "handoff")
        generated_text = state.get("generated_text")
        if "user_requested_handoff" in state.get("risk_tags", []):
            text = "好的，这就为您转接人工～"
        elif state.get("forbidden_claims"):
            text = generated_text
        else:
            text = (
                "宝宝，这个问题需要人工客服进一步确认，"
                "我已为您记录并转接，请稍候。"
            )
        reply = AgentReply(
            conversation_id=self._message(state).external_conversation_id,
            decision=Decision.handoff,
            text=text,
            citations=[
                hit.citation() for hit in self.knowledge.restore_hits(state.get("hits", []))
            ],
            handoff_reason=state.get("handoff_reason", "需要人工处理"),
            risk_tags=state.get("risk_tags", []),
            graph_trace=trace,
        )
        return {"reply": reply.model_dump(mode="json"), "trace": trace}

    async def handle(self, message: IncomingMessage) -> AgentReply:
        existing = await self.store.find_reply(message.platform, message.external_message_id)
        if existing:
            return existing
        config = {
            "configurable": {
                "thread_id": f"{message.platform.value}:{message.external_conversation_id}"
            }
        }
        result = await self.graph.ainvoke(
            {
                "message": message.model_dump(mode="json"),
                "trace": [],
                "hits": [],
                "direct_faq": False,
                "generated_text": "",
                "forbidden_claims": [],
                "handoff_reason": "",
                "risk_tags": [],
                "response_decision": Decision.answered.value,
            },
            config=config,
        )
        reply = AgentReply.model_validate(result["reply"])
        safe_message = message.model_copy(update={"text": self.policy.redact_sensitive_data(message.text)})
        await self.store.append(ConversationEvent(incoming=safe_message, reply=reply))
        return reply
