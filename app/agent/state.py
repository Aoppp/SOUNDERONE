from __future__ import annotations

from typing import TypedDict

class AgentState(TypedDict, total=False):
    message: dict
    trace: list[str]
    risk: dict
    retrieval_query: str
    conversation_intent: str
    query_intent: str
    topic_query: str
    topic_intent: str
    topic_document_ids: list[str]
    topic_products: list[str]
    contextual_followup: bool
    followup_kind: str
    knowledge_types: list[str]
    recognized_faq: bool
    explicit_product: str
    response_decision: str
    last_product: str
    hits: list[dict]
    direct_faq: bool
    generated_text: str
    forbidden_claims: list[str]
    handoff_reason: str
    risk_tags: list[str]
    reply: dict
