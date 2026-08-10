from collections import defaultdict

from app.models import AgentReply, ConversationEvent, Platform


class InMemoryConversationStore:
    def __init__(self):
        self._events: dict[str, list[ConversationEvent]] = defaultdict(list)
        self._message_replies: dict[tuple[Platform, str], AgentReply] = {}

    async def append(self, event: ConversationEvent) -> None:
        self._events[event.incoming.external_conversation_id].append(event)
        self._message_replies[(event.incoming.platform, event.incoming.external_message_id)] = event.reply

    async def get(self, conversation_id: str) -> list[ConversationEvent]:
        return list(self._events.get(conversation_id, []))

    async def find_reply(self, platform: Platform, message_id: str) -> AgentReply | None:
        return self._message_replies.get((platform, message_id))
