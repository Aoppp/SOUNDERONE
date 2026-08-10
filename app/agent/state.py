from __future__ import annotations

from typing import TypedDict

class AgentState(TypedDict, total=False):
    message: dict
    trace: list[str]
    risk: dict
    retrieval_query: str
    conversation_intent: str
    response_decision: str
    last_product: str
    hits: list[dict]
    generated_text: str
    forbidden_claims: list[str]
    handoff_reason: str
    risk_tags: list[str]
    reply: dict
