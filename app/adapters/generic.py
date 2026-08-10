from typing import Any

from app.adapters.base import PlatformAdapter
from app.models import AgentReply, IncomingMessage, Platform


class GenericAdapter(PlatformAdapter):
    """Development contract. Replace parsing/serialization per official platform API."""

    def __init__(self, platform: Platform):
        self.platform = platform

    def parse(self, payload: dict[str, Any]) -> IncomingMessage:
        return IncomingMessage(
            platform=self.platform,
            external_message_id=str(payload["message_id"]),
            external_conversation_id=str(payload["conversation_id"]),
            external_user_id=str(payload["user_id"]),
            text=payload["text"],
            metadata=payload.get("metadata", {}),
        )

    def serialize(self, reply: AgentReply) -> dict[str, Any]:
        return {
            "reply_id": reply.reply_id,
            "conversation_id": reply.conversation_id,
            "decision": reply.decision.value,
            "text": reply.text,
            "handoff": reply.decision.value != "answered",
            "handoff_reason": reply.handoff_reason,
            "citations": [citation.model_dump() for citation in reply.citations],
        }
