from typing import Any

from pydantic import ValidationError

from app.models import AgentReply, IncomingMessage, Platform


class DouyinAdapter:
    """Normalized Douyin contract used until official callback credentials are available."""

    def __init__(self, platform: Platform = Platform.douyin):
        if platform not in {Platform.douyin, Platform.simulator}:
            raise ValueError("only douyin and simulator are supported")
        self.platform = platform

    def parse(self, payload: dict[str, Any]) -> IncomingMessage:
        try:
            return IncomingMessage(
                platform=self.platform,
                external_message_id=str(payload["message_id"]),
                external_conversation_id=str(payload["conversation_id"]),
                external_user_id=str(payload["user_id"]),
                text=payload["text"],
                metadata=payload.get("metadata", {}),
            )
        except ValidationError:
            raise

    @staticmethod
    def serialize(reply: AgentReply) -> dict[str, Any]:
        return {
            "reply_id": reply.reply_id,
            "conversation_id": reply.conversation_id,
            "decision": reply.decision.value,
            "text": reply.text,
            "handoff": reply.decision.value != "answered",
            "handoff_reason": reply.handoff_reason,
            "risk_tags": reply.risk_tags,
            "graph_trace": reply.graph_trace,
            "citations": [citation.model_dump() for citation in reply.citations],
        }
