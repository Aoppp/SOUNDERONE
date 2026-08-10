from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class Platform(str, Enum):
    taobao = "taobao"
    douyin = "douyin"
    jd = "jd"
    pinduoduo = "pinduoduo"
    xiaohongshu = "xiaohongshu"
    wechat_store = "wechat_store"
    kuaishou = "kuaishou"
    mogujie = "mogujie"
    dewu = "dewu"
    simulator = "simulator"


class Decision(str, Enum):
    answered = "answered"
    handoff = "handoff"
    safe_fallback = "safe_fallback"


class IncomingMessage(BaseModel):
    platform: Platform
    external_message_id: str
    external_conversation_id: str
    external_user_id: str
    text: str = Field(min_length=1, max_length=4000)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


class Citation(BaseModel):
    document_id: str
    title: str
    score: float
    source_sheet: str | None = None
    source_row: int | None = None
    category: str | None = None


class AgentReply(BaseModel):
    reply_id: str = Field(default_factory=lambda: str(uuid4()))
    conversation_id: str
    decision: Decision
    text: str
    citations: list[Citation] = Field(default_factory=list)
    handoff_reason: str | None = None
    risk_tags: list[str] = Field(default_factory=list)


class ConversationEvent(BaseModel):
    incoming: IncomingMessage
    reply: AgentReply
