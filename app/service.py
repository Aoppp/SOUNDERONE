from app.config import Settings
from app.knowledge import LocalKnowledgeBase
from app.llm import LanguageModel
from app.models import AgentReply, ConversationEvent, Decision, IncomingMessage
from app.policy import SafetyPolicy
from app.store import InMemoryConversationStore


class CustomerServiceAgent:
    def __init__(
        self,
        settings: Settings,
        knowledge: LocalKnowledgeBase,
        policy: SafetyPolicy,
        llm: LanguageModel,
        store: InMemoryConversationStore,
    ):
        self.settings = settings
        self.knowledge = knowledge
        self.policy = policy
        self.llm = llm
        self.store = store

    async def handle(self, message: IncomingMessage) -> AgentReply:
        existing = await self.store.find_reply(message.platform, message.external_message_id)
        if existing:
            return existing
        risk = self.policy.evaluate_incoming(message.text)
        if risk.must_handoff:
            reply = AgentReply(
                conversation_id=message.external_conversation_id,
                decision=Decision.handoff,
                text="宝宝，您的情况需要人工客服进一步处理，我这边马上为您转接，请稍候。",
                handoff_reason=risk.reason,
                risk_tags=risk.risk_tags,
            )
            return await self._record(message, reply)

        hits = self.knowledge.search(message.text)
        reliable = hits and hits[0].score >= self.settings.knowledge_min_score
        if not reliable:
            reply = AgentReply(
                conversation_id=message.external_conversation_id,
                decision=Decision.handoff,
                text="宝宝，这个问题我暂时没有查到可靠资料，为避免给您错误信息，我帮您转接人工确认。",
                handoff_reason="知识库无可靠答案",
                risk_tags=["low_knowledge_confidence"],
            )
            return await self._record(message, reply)

        if not self.policy.is_business_hours() and hits[0].score < 0.45:
            reply = AgentReply(
                conversation_id=message.external_conversation_id,
                decision=Decision.safe_fallback,
                text="宝宝，目前是非人工服务时段，这个问题需要进一步确认，我已为您留言，人工客服上班后会继续处理。",
                handoff_reason="非工作时段且知识置信度不足",
                risk_tags=["off_hours_restricted"],
            )
            return await self._record(message, reply)

        generated = await self.llm.answer(message.text, hits)
        safe_text, forbidden = self.policy.sanitize_output(generated)
        decision = Decision.handoff if forbidden else Decision.answered
        reply = AgentReply(
            conversation_id=message.external_conversation_id,
            decision=decision,
            text=safe_text,
            citations=[hit.citation() for hit in hits],
            handoff_reason="生成内容触发禁用词" if forbidden else None,
            risk_tags=[f"forbidden_claim:{word}" for word in forbidden],
        )
        return await self._record(message, reply)

    async def _record(self, message: IncomingMessage, reply: AgentReply) -> AgentReply:
        safe_message = message.model_copy(update={"text": self.policy.redact_sensitive_data(message.text)})
        await self.store.append(ConversationEvent(incoming=safe_message, reply=reply))
        return reply
