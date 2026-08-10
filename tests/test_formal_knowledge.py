import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.ingestion.xlsx import build_knowledge
from app.rag import HybridKnowledgeBase
from app.rag.embeddings import HashDenseEmbedder
from app.main import create_app


KNOWLEDGE_PATH = Path("knowledge/sounderone_knowledge.json")
REPORT_PATH = Path("knowledge/build_report.json")
SOURCE_PATH = Path("产品话术汇总完整版本.xlsx")


def make_knowledge() -> HybridKnowledgeBase:
    return HybridKnowledgeBase(KNOWLEDGE_PATH, HashDenseEmbedder())


def test_generated_knowledge_has_expected_safety_partition():
    payload = json.loads(KNOWLEDGE_PATH.read_text(encoding="utf-8"))
    statuses = [document["status"] for document in payload["documents"]]
    assert len(statuses) == 287
    assert statuses.count("active") == 210
    assert statuses.count("review_required") == 39
    assert statuses.count("handoff_only") == 38


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


def test_pregnancy_question_handoffs_before_knowledge_generation():
    settings = Settings(
        llm_provider="mock",
        knowledge_path=KNOWLEDGE_PATH,
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


@pytest.mark.skipif(not SOURCE_PATH.exists(), reason="private source workbook is intentionally not committed")
def test_local_source_rebuild_is_deterministic():
    knowledge, report = build_knowledge(SOURCE_PATH)
    committed = json.loads(KNOWLEDGE_PATH.read_text(encoding="utf-8"))
    assert knowledge == committed
    assert report["summary"]["documents"] == 287
    assert report["summary"]["duplicates_merged"] == 4
