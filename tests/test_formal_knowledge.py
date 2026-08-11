import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.ingestion.xlsx import build_knowledge, split_knowledge_payload
from app.rag import HybridKnowledgeBase
from app.rag.embeddings import HashDenseEmbedder
from app.main import create_app


KNOWLEDGE_PATH = Path("knowledge/sounderone_knowledge.json")
REPORT_PATH = Path("knowledge/build_report.json")
PRODUCT_KNOWLEDGE_PATH = Path("knowledge/product_knowledge.json")
FAQ_KNOWLEDGE_PATH = Path("knowledge/customer_faq.json")
SOURCE_PATH = Path("source_materials/产品话术汇总完整版本.xlsx")


def make_knowledge() -> HybridKnowledgeBase:
    return HybridKnowledgeBase(KNOWLEDGE_PATH, HashDenseEmbedder())


def test_generated_knowledge_has_expected_safety_partition():
    payload = json.loads(KNOWLEDGE_PATH.read_text(encoding="utf-8"))
    statuses = [document["status"] for document in payload["documents"]]
    assert len(statuses) == 287
    assert statuses.count("active") == 210
    assert statuses.count("review_required") == 39
    assert statuses.count("handoff_only") == 38


def test_product_and_faq_files_are_a_lossless_split():
    combined = json.loads(KNOWLEDGE_PATH.read_text(encoding="utf-8"))
    expected_product, expected_faq = split_knowledge_payload(combined)
    product = json.loads(PRODUCT_KNOWLEDGE_PATH.read_text(encoding="utf-8"))
    faq = json.loads(FAQ_KNOWLEDGE_PATH.read_text(encoding="utf-8"))
    assert product == expected_product
    assert faq == expected_faq
    assert len(product["documents"]) == 64
    assert len(faq["documents"]) == 223
    assert all(item["knowledge_type"] == "product" for item in product["documents"])
    assert all(item["knowledge_type"] == "faq" for item in faq["documents"])


def test_generated_knowledge_contains_no_phone_or_transaction_numbers():
    payload = json.loads(KNOWLEDGE_PATH.read_text(encoding="utf-8"))
    searchable_content = "\n".join(
        document["title"] + "\n" + document["content"] for document in payload["documents"]
    )
    assert re.search(r"(?<!\d)1[3-9]\d{9}(?!\d)", searchable_content) is None
    assert re.search(r"(?<!\d)\d{15,}(?!\d)", searchable_content) is None
    assert "湖北省武汉市东西湖区" not in searchable_content
    assert "仓库退货组" not in searchable_content
    assert "马鑫常用话术" not in searchable_content

    report_content = REPORT_PATH.read_text(encoding="utf-8")
    assert re.search(r"(?<!\d)1[3-9]\d{9}(?!\d)", report_content) is None
    assert "仓库退货组" not in report_content


def test_order_sheets_are_excluded_and_conflicts_are_reported():
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    sheets = {item["sheet"]: item for item in report["sheets"]}
    assert sheets["CXD"]["decision"] == "excluded"
    assert sheets["无所谓"]["decision"] == "excluded"
    assert sheets["Sheet14"]["decision"] == "excluded"
    assert report["summary"]["conflicts"] == 46
    assert any(conflict["type"] == "canonical_numeric_conflict" for conflict in report["conflicts"])


def test_product_usage_retrieval_is_concentration_specific_and_traceable():
    knowledge = make_knowledge()
    hits = knowledge.search("5%传明酸怎么使用")
    assert hits
    assert hits[0].document.category == "product_usage"
    assert hits[0].document.source_sheet == "三蛋丸"
    assert hits[0].document.source_row == 3
    assert "10%传明酸" not in hits[0].document.title


def test_conflicting_ergothioneine_concentration_is_not_searchable():
    knowledge = make_knowledge()
    hits = knowledge.search("麦角硫因浓度是多少", limit=10)
    assert hits
    assert "0.5%" in hits[0].document.content
    assert all("2%麦角硫因" not in hit.document.title for hit in hits)


def test_missing_vcip_usage_does_not_return_unrelated_documents():
    knowledge = make_knowledge()
    hits = knowledge.search("VCIP怎么用")
    assert hits == []


def test_missing_shipping_answer_does_not_match_product_effectiveness():
    knowledge = make_knowledge()
    assert knowledge.search("多久发货") == []


def test_recommendation_retrieval_requires_matching_customer_goal():
    knowledge = make_knowledge()
    beauty_hits = knowledge.search("有什么美白产品推荐")
    assert beauty_hits
    assert any("夜猫子精华" in hit.document.title for hit in beauty_hits)
    assert all(
        "美白" in hit.document.index_text or "提亮" in hit.document.index_text
        for hit in beauty_hits
    )

    anti_aging_hits = knowledge.search("那有没有什么抗衰的呢")
    assert anti_aging_hits
    assert "玻色因面霜" in anti_aging_hits[0].document.title
    assert knowledge.search("有去黑头产品推荐吗") == []


def test_comparison_and_hair_pairing_use_the_workbook_semantics():
    knowledge = make_knowledge()
    comparison_hits = knowledge.search("5%和10%传明酸有什么区别")
    assert comparison_hits[0].document.category == "product_comparison"
    assert comparison_hits[0].document.source_row == 5

    pairing_hits = knowledge.search("木洗发水和火洗发水怎么搭配")
    assert pairing_hits[0].document.category == "product_note"
    assert pairing_hits[0].document.source_row == 21
    assert "净澈控油沁爽洗发水" in pairing_hits[0].document.title


def test_formal_knowledge_runs_through_agent_with_source_citation():
    settings = Settings(
        llm_provider="mock",
        knowledge_path=KNOWLEDGE_PATH,
        qdrant_path=None,
        qdrant_url=None,
        webhook_secret="test-secret",
        admin_api_key="test-admin",
        business_hours_start="00:00",
        business_hours_end="23:59",
    )
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/v1/webhooks/simulator",
            headers={"X-Webhook-Secret": "test-secret"},
            json={
                "message_id": "formal-1",
                "conversation_id": "formal-conversation-1",
                "user_id": "formal-user-1",
                "text": "5%传明酸怎么使用？",
            },
        )
    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "answered"
    assert body["citations"][0]["source_sheet"] == "三蛋丸"
    assert body["citations"][0]["source_row"] == 3


def test_agent_answers_grounded_recommendation_and_handoffs_when_missing():
    settings = Settings(
        llm_provider="mock",
        knowledge_path=KNOWLEDGE_PATH,
        qdrant_path=None,
        qdrant_url=None,
        webhook_secret="test-secret",
        admin_api_key="test-admin",
        business_hours_start="00:00",
        business_hours_end="23:59",
    )
    headers = {"X-Webhook-Secret": "test-secret"}
    with TestClient(create_app(settings)) as client:
        recommendation = client.post(
            "/v1/webhooks/simulator",
            headers=headers,
            json={
                "message_id": "recommendation-1",
                "conversation_id": "recommendation-conversation-1",
                "user_id": "recommendation-user",
                "text": "有什么美白产品推荐",
            },
        ).json()
        follow_up = client.post(
            "/v1/webhooks/simulator",
            headers=headers,
            json={
                "message_id": "recommendation-follow-up-1",
                "conversation_id": "recommendation-conversation-1",
                "user_id": "recommendation-user",
                "text": "那有没有什么抗衰的呢？",
            },
        ).json()
        missing = client.post(
            "/v1/webhooks/simulator",
            headers=headers,
            json={
                "message_id": "recommendation-2",
                "conversation_id": "recommendation-conversation-2",
                "user_id": "recommendation-user",
                "text": "有去黑头产品推荐吗",
            },
        ).json()

    assert recommendation["decision"] == "answered"
    assert any("夜猫子精华" in citation["title"] for citation in recommendation["citations"])
    assert "clarify_response" not in recommendation["graph_trace"]
    assert recommendation["graph_trace"][1:5] == [
        "intent_router",
        "rewrite_query",
        "route_knowledge",
        "hybrid_retrieve",
    ]
    assert follow_up["decision"] == "answered"
    assert "玻色因面霜" in follow_up["citations"][0]["title"]
    assert follow_up["citations"][0]["category"] == "product_overview"
    assert "out_of_scope_response" not in follow_up["graph_trace"]
    assert "clarify_response" not in follow_up["graph_trace"]
    assert missing["decision"] == "handoff"
    assert missing["handoff_reason"] == "知识库无可靠答案"
    assert missing["citations"] == []


def test_pregnancy_question_handoffs_before_knowledge_generation():
    settings = Settings(
        llm_provider="mock",
        knowledge_path=KNOWLEDGE_PATH,
        qdrant_path=None,
        qdrant_url=None,
        webhook_secret="test-secret",
        admin_api_key="test-admin",
    )
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/v1/webhooks/simulator",
            headers={"X-Webhook-Secret": "test-secret"},
            json={
                "message_id": "formal-2",
                "conversation_id": "formal-conversation-2",
                "user_id": "formal-user-2",
                "text": "孕妇可以用5%传明酸吗？",
            },
        )
    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "handoff"
    assert "sensitive_population" in body["risk_tags"]


def test_langgraph_resolves_product_reference_across_turns():
    settings = Settings(
        llm_provider="mock",
        knowledge_path=KNOWLEDGE_PATH,
        qdrant_path=None,
        qdrant_url=None,
        webhook_secret="test-secret",
        admin_api_key="test-admin",
        business_hours_start="00:00",
        business_hours_end="23:59",
    )
    headers = {"X-Webhook-Secret": "test-secret"}
    with TestClient(create_app(settings)) as client:
        first = client.post(
            "/v1/webhooks/simulator",
            headers=headers,
            json={
                "message_id": "context-1",
                "conversation_id": "context-conversation",
                "user_id": "context-user",
                "text": "5%传明酸是什么？",
            },
        )
        second = client.post(
            "/v1/webhooks/simulator",
            headers=headers,
            json={
                "message_id": "context-2",
                "conversation_id": "context-conversation",
                "user_id": "context-user",
                "text": "这个怎么使用？",
            },
        )
    assert first.json()["decision"] == "answered"
    assert second.json()["decision"] == "answered"
    assert second.json()["citations"][0]["category"] == "product_usage"
    assert second.json()["citations"][0]["source_row"] == 3


def test_nonsense_does_not_retrieve_even_when_conversation_has_product_context():
    settings = Settings(
        llm_provider="mock",
        knowledge_path=KNOWLEDGE_PATH,
        qdrant_path=None,
        qdrant_url=None,
        webhook_secret="test-secret",
        admin_api_key="test-admin",
        business_hours_start="00:00",
        business_hours_end="23:59",
    )
    headers = {"X-Webhook-Secret": "test-secret"}
    with TestClient(create_app(settings)) as client:
        first = client.post(
            "/v1/webhooks/simulator",
            headers=headers,
            json={
                "message_id": "context-nonsense-1",
                "conversation_id": "context-nonsense-conversation",
                "user_id": "context-user",
                "text": "5%传明酸是什么？",
            },
        )
        second = client.post(
            "/v1/webhooks/simulator",
            headers=headers,
            json={
                "message_id": "context-nonsense-2",
                "conversation_id": "context-nonsense-conversation",
                "user_id": "context-user",
                "text": "他好",
            },
        )
    assert first.json()["decision"] == "answered"
    body = second.json()
    assert body["decision"] == "safe_fallback"
    assert body["citations"] == []
    assert "hybrid_retrieve" not in body["graph_trace"]


@pytest.mark.skipif(not SOURCE_PATH.exists(), reason="private source workbook is intentionally not committed")
def test_local_source_rebuild_is_deterministic():
    knowledge, report = build_knowledge(SOURCE_PATH)
    committed = json.loads(KNOWLEDGE_PATH.read_text(encoding="utf-8"))
    assert knowledge == committed
    assert report["summary"]["documents"] == 287
    assert report["summary"]["duplicates_merged"] == 4
