from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.agent.grounding import DeterministicGroundingVerifier
from app.config import Settings
from app.main import create_app
from app.rag import SearchHit
from app.rag.embeddings import HashDenseEmbedder
from app.rag.retriever import HybridKnowledgeBase


KNOWLEDGE = Path("knowledge/sounderone_knowledge.json")


@pytest.fixture
def knowledge():
    instance = HybridKnowledgeBase(KNOWLEDGE, HashDenseEmbedder())
    yield instance
    instance.close()


@pytest.fixture
def client():
    app = create_app(
        Settings(
            llm_provider="mock",
            embedding_provider="hash",
            embedding_dimensions=384,
            knowledge_path=KNOWLEDGE,
            qdrant_path=None,
            webhook_secret="test-secret",
            business_hours_start="00:00",
            business_hours_end="23:59",
        )
    )
    with TestClient(app) as value:
        yield value


def send(client: TestClient, case_id: str, text: str, conversation: str | None = None):
    return client.post(
        "/v1/webhooks/simulator",
        headers={"X-Webhook-Secret": "test-secret"},
        json={
            "message_id": case_id,
            "conversation_id": conversation or case_id,
            "user_id": "routing-test",
            "text": text,
        },
    ).json()


def test_product_entity_resolver_covers_abbreviations(knowledge):
    assert knowledge.identify_product("AM质地为什么这么稀") == "AM洗发水"
    assert knowledge.identify_product("VCIP怎么用") == "30%VCIP光感清透精华油"
    assert knowledge.identify_product("你好，B5含量是多少") == "B5洗发水"
    assert knowledge.identify_product("euk134怎么用") == "EUK-134精华"


def test_mixed_greeting_and_product_question_enters_rag(client):
    body = send(client, "ROUTE-004-regression", "你好，B5含量是多少")
    assert "out_of_scope_response" not in body["graph_trace"]
    assert "hybrid_retrieve" in body["graph_trace"]


def test_am_faq_is_not_blocked_before_rag(client):
    body = send(client, "FAQ-009-regression", "AM质地为什么这么稀")
    assert body["decision"] == "answered"
    assert "direct_faq_answer" in body["graph_trace"]
    assert body["citations"][0]["source_row"] == 62


def test_vcip_is_recognized_then_handoffs_when_usage_is_unknown(client):
    body = send(client, "VCIP-regression", "VCIP怎么用")
    assert body["decision"] == "handoff"
    assert "clarify_response" not in body["graph_trace"]
    assert body["handoff_reason"] == "知识库无可靠答案"


def test_plural_reference_without_context_is_clarified(client):
    body = send(client, "CTX-missing-regression", "这几款哪个更适合油皮")
    assert body["decision"] == "safe_fallback"
    assert "clarify_response" in body["graph_trace"]
    assert not body["citations"]


def test_grounding_rejects_unsupported_numeric_claim(knowledge):
    hit = knowledge.search("B5洗发水是什么香型", knowledge_types={"faq"})[0]
    verifier = DeterministicGroundingVerifier(knowledge.entity_resolver)
    result = verifier.verify(
        "宝宝，B5洗发水是橙香，B5含量是20%哦。",
        "B5洗发水是什么香型",
        [SearchHit(hit.document, hit.score, hit.retrieval_channels)],
    )
    assert not result.supported
    assert "20%" in result.unsupported_claims


def test_grounding_accepts_supported_numeric_claim(knowledge):
    hit = knowledge.search("B5洗发水B5含量", knowledge_types={"faq"})[0]
    verifier = DeterministicGroundingVerifier(knowledge.entity_resolver)
    result = verifier.verify("宝宝，B5含量是0.20%。", "B5含量是多少", [hit])
    assert result.supported
