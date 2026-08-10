from __future__ import annotations

import re

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from app.agent.state import AgentState
from app.config import Settings
from app.llm import LanguageModel
from app.models import AgentReply, ConversationEvent, Decision, IncomingMessage
from app.policy import SafetyPolicy
from app.rag import HybridKnowledgeBase
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
        builder.add_node("understand_query", self._understand_query)
        builder.add_node("smalltalk_response", self._smalltalk_response)
        builder.add_node("clarify_response", self._clarify_response)
        builder.add_node("hybrid_retrieve", self._hybrid_retrieve)
        builder.add_node("relevance_gate", self._relevance_gate)
        builder.add_node("generate_answer", self._generate_answer)
        builder.add_node("output_guard", self._output_guard)
        builder.add_node("finalize_response", self._finalize_response)
        builder.add_node("handoff", self._handoff)

        builder.add_edge(START, "safety_guard")
        builder.add_conditional_edges(
            "safety_guard",
            self._route_after_safety,
            {"continue": "understand_query", "handoff": "handoff"},
        )
        builder.add_conditional_edges(
            "understand_query",
            self._route_after_understanding,
            {
                "smalltalk": "smalltalk_response",
                "clarify": "clarify_response",
                "retrieve": "hybrid_retrieve",
            },
        )
        builder.add_edge("smalltalk_response", "output_guard")
        builder.add_edge("clarify_response", "output_guard")
        builder.add_edge("hybrid_retrieve", "relevance_gate")
        builder.add_conditional_edges(
            "relevance_gate",
            self._route_after_relevance,
            {"generate": "generate_answer", "handoff": "handoff"},
        )
        builder.add_edge("generate_answer", "output_guard")
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

    def _understand_query(self, state: AgentState) -> dict:
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
                "trace": self._step(state, "understand_query"),
            }
        explicit_product = self.knowledge.identify_product(text)
        last_product = explicit_product or state.get("last_product", "")
        refers_to_context = any(word in text for word in ("这个", "它", "这款", "刚才那个"))
        has_supported_cue = any(cue in text for cue in self.SUPPORT_CUES)
        has_standalone_service_cue = any(cue in text for cue in self.STANDALONE_SERVICE_CUES)
        needs_clarification = (
            (refers_to_context and not last_product)
            or (not explicit_product and not last_product and not has_standalone_service_cue)
            or (
                not explicit_product
                and bool(last_product)
                and not (has_supported_cue or has_standalone_service_cue)
            )
        )
        if needs_clarification:
            return {
                "conversation_intent": "clarification",
                "retrieval_query": "",
                "trace": self._step(state, "understand_query"),
            }
        retrieval_query = f"{last_product} {text}" if last_product and refers_to_context else text
        return {
            "retrieval_query": retrieval_query,
            "conversation_intent": "knowledge_query",
            "last_product": last_product,
            "trace": self._step(state, "understand_query"),
        }

    @staticmethod
    def _route_after_understanding(state: AgentState) -> str:
        intent = state.get("conversation_intent")
        if intent == "smalltalk":
            return "smalltalk"
        if intent == "clarification":
            return "clarify"
        return "retrieve"

    def _smalltalk_response(self, state: AgentState) -> dict:
        return {
            "generated_text": (
                "宝宝你好～我是 SounderOne 智能客服。"
                "你可以直接问我产品用法、成分搭配或其他售前问题。"
            ),
            "hits": [],
            "trace": self._step(state, "smalltalk_response"),
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

    def _hybrid_retrieve(self, state: AgentState) -> dict:
        hits = self.knowledge.search(state["retrieval_query"])
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
            update.update(
                handoff_reason="知识库无可靠答案",
                risk_tags=["low_knowledge_confidence"],
            )
        elif not self.policy.is_business_hours() and hits[0]["score"] < 0.62:
            update.update(
                handoff_reason="非工作时段且知识置信度不足",
                risk_tags=["off_hours_restricted"],
            )
        else:
            update.update(handoff_reason="", risk_tags=[])
        return update

    @staticmethod
    def _route_after_relevance(state: AgentState) -> str:
        return "handoff" if state.get("handoff_reason") else "generate"

    async def _generate_answer(self, state: AgentState) -> dict:
        generated = await self.llm.answer(
            self._message(state).text,
            self.knowledge.restore_hits(state["hits"]),
        )
        return {"generated_text": generated, "trace": self._step(state, "generate_answer")}

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
        text = generated_text if state.get("forbidden_claims") else (
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
