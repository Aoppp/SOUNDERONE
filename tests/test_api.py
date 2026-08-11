from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def make_client() -> TestClient:
    settings = Settings(
        llm_provider="mock",
        knowledge_path=Path("knowledge/sample.json"),
        qdrant_path=None,
        qdrant_url=None,
        webhook_secret="test-secret",
        admin_api_key="test-admin",
        business_hours_start="00:00",
        business_hours_end="23:59",
    )
    return TestClient(create_app(settings))


def make_split_knowledge_client() -> TestClient:
    settings = Settings(
        knowledge_path=None,
        product_knowledge_path=Path("knowledge/product_knowledge.json"),
        faq_knowledge_path=Path("knowledge/customer_faq.json"),
        llm_provider="mock",
        qdrant_path=None,
        qdrant_url=None,
        webhook_secret="test-secret",
        admin_api_key="test-admin",
        business_hours_start="00:00",
        business_hours_end="23:59",
    )
    return TestClient(create_app(settings))


def test_health():
    with make_client() as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["knowledge_documents"] == 3
        assert response.json()["agent_runtime"] == "langgraph"
        assert response.json()["llm_provider"] == "mock"
        assert response.json()["retrieval"] == "qdrant_dense_bm25_rrf"
        assert response.json()["platforms"] == ["douyin", "simulator"]


def test_application_loads_product_and_faq_files_together():
    with make_split_knowledge_client() as client:
        health = client.get("/health").json()
        assert health["knowledge_documents"] == 287
        assert health["active_knowledge_documents"] == 210
        assert health["knowledge_types"] == {"faq": 223, "product": 64}

        response = client.post(
            "/v1/webhooks/simulator",
            headers={"X-Webhook-Secret": "test-secret"},
            json={
                "message_id": "split-knowledge-1",
                "conversation_id": "split-knowledge-conversation",
                "user_id": "user-1",
                "text": "5%传明酸怎么使用？",
            },
        )
        body = response.json()
        assert body["decision"] == "answered"
        assert body["citations"]
        assert {citation["knowledge_type"] for citation in body["citations"]} <= {
            "product",
            "faq",
        }
        assert all(citation["score"] >= 0.48 for citation in body["citations"])


def test_browser_tester_and_static_assets_are_served():
    with make_client() as client:
        page = client.get("/tester")
        assert page.status_code == 200
        assert "SOUNDERONE Agent Lab" in page.text
        assert 'id="messageForm"' in page.text
        assert 'src="/static/tester.js"' in page.text

        script = client.get("/static/tester.js")
        stylesheet = client.get("/static/tester.css")
        assert script.status_code == 200
        assert 'fetch("/v1/webhooks/simulator"' in script.text
        assert stylesheet.status_code == 200
        assert ".chat-panel" in stylesheet.text


def test_webhook_answers_grounded_question_and_records_history():
    payload = {
        "message_id": "msg-1",
        "conversation_id": "conversation-1",
        "user_id": "user-1",
        "text": "多久发货？",
    }
    with make_client() as client:
        response = client.post(
            "/v1/webhooks/douyin",
            headers={"X-Webhook-Secret": "test-secret"},
            json=payload,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["decision"] == "answered"
        assert "根据现有资料" not in body["text"]
        assert body["citations"][0]["document_id"] == "demo-shipping-001"
        assert body["citations"][0]["knowledge_type"] == "faq"
        assert body["citations"][0]["retrieval_channels"] == ["bm25", "dense"]
        assert body["graph_trace"] == [
            "safety_guard",
            "intent_router",
            "rewrite_query",
            "route_knowledge",
            "hybrid_retrieve",
            "relevance_gate",
            "generate_answer",
            "output_guard",
            "finalize_response",
        ]

        history = client.get(
            "/v1/conversations/conversation-1", headers={"X-Admin-Key": "test-admin"}
        )
        assert history.status_code == 200
        assert len(history.json()) == 1


def test_pure_greeting_bypasses_rag_and_returns_welcome():
    payload = {
        "message_id": "greeting-1",
        "conversation_id": "greeting-conversation",
        "user_id": "user-1",
        "text": "你好",
    }
    with make_client() as client:
        response = client.post(
            "/v1/webhooks/simulator",
            headers={"X-Webhook-Secret": "test-secret"},
            json=payload,
        )
    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "answered"
    assert "SOUNDERONE 智能客服" in body["text"]
    assert body["citations"] == []
    assert body["graph_trace"] == [
        "safety_guard",
        "intent_router",
        "smalltalk_response",
        "output_guard",
        "finalize_response",
    ]


def test_greeting_with_business_question_still_uses_hybrid_rag():
    payload = {
        "message_id": "greeting-question-1",
        "conversation_id": "greeting-question-conversation",
        "user_id": "user-1",
        "text": "你好，多久发货？",
    }
    with make_client() as client:
        response = client.post(
            "/v1/webhooks/simulator",
            headers={"X-Webhook-Secret": "test-secret"},
            json=payload,
        )
    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "answered"
    assert body["citations"][0]["document_id"] == "demo-shipping-001"
    assert "hybrid_retrieve" in body["graph_trace"]


def test_out_of_domain_messages_return_brand_scope_without_rag():
    messages = ("他好", "随便说说", "天气怎么样", "……")
    with make_client() as client:
        for index, text in enumerate(messages):
            response = client.post(
                "/v1/webhooks/simulator",
                headers={"X-Webhook-Secret": "test-secret"},
                json={
                    "message_id": f"nonsense-{index}",
                    "conversation_id": f"nonsense-conversation-{index}",
                    "user_id": "user-1",
                    "text": text,
                },
            )
            assert response.status_code == 200
            body = response.json()
            assert body["decision"] == "safe_fallback"
            assert body["handoff"] is False
            assert "SOUNDERONE" in body["text"]
            assert "王叔" not in body["text"]
            assert body["citations"] == []
            assert body["graph_trace"] == [
                "safety_guard",
                "intent_router",
                "out_of_scope_response",
                "output_guard",
                "finalize_response",
            ]


def test_product_question_without_product_name_asks_for_clarification():
    with make_client() as client:
        response = client.post(
            "/v1/webhooks/simulator",
            headers={"X-Webhook-Secret": "test-secret"},
            json={
                "message_id": "missing-product-1",
                "conversation_id": "missing-product-conversation",
                "user_id": "user-1",
                "text": "怎么用",
            },
        )
    body = response.json()
    assert body["decision"] == "safe_fallback"
    assert "产品名称" in body["text"]
    assert body["graph_trace"] == [
        "safety_guard",
        "intent_router",
        "clarify_response",
        "output_guard",
        "finalize_response",
    ]


def test_contextless_pronoun_asks_for_product_name():
    payload = {
        "message_id": "pronoun-1",
        "conversation_id": "pronoun-conversation",
        "user_id": "user-1",
        "text": "这个怎么使用？",
    }
    with make_client() as client:
        response = client.post(
            "/v1/webhooks/simulator",
            headers={"X-Webhook-Secret": "test-secret"},
            json=payload,
        )
    body = response.json()
    assert body["decision"] == "safe_fallback"
    assert body["citations"] == []
    assert "clarify_response" in body["graph_trace"]


def test_webhook_handoffs_refund_request():
    payload = {
        "message_id": "msg-2",
        "conversation_id": "conversation-2",
        "user_id": "user-2",
        "text": "我要退款",
    }
    with make_client() as client:
        response = client.post(
            "/v1/webhooks/douyin",
            headers={"X-Webhook-Secret": "test-secret"},
            json=payload,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["decision"] == "handoff"
        assert body["graph_trace"] == ["safety_guard", "handoff"]


def test_webhook_requires_secret():
    with make_client() as client:
        response = client.post("/v1/webhooks/douyin", json={})
        assert response.status_code == 401


def test_malformed_authenticated_webhook_returns_422():
    with make_client() as client:
        response = client.post(
            "/v1/webhooks/douyin",
            headers={"X-Webhook-Secret": "test-secret"},
            json={"text": "缺少消息标识"},
        )
        assert response.status_code == 422


def test_duplicate_platform_message_is_idempotent():
    payload = {
        "message_id": "same-message",
        "conversation_id": "conversation-idempotent",
        "user_id": "user-1",
        "text": "多久发货？",
    }
    with make_client() as client:
        headers = {"X-Webhook-Secret": "test-secret"}
        first = client.post("/v1/webhooks/douyin", headers=headers, json=payload).json()
        second = client.post("/v1/webhooks/douyin", headers=headers, json=payload).json()
        assert first["reply_id"] == second["reply_id"]
        history = client.get(
            "/v1/conversations/conversation-idempotent",
            headers={"X-Admin-Key": "test-admin"},
        )
        assert len(history.json()) == 1


def test_admin_endpoint_requires_admin_key():
    with make_client() as client:
        assert client.get("/v1/conversations/anything").status_code == 401


def test_sensitive_data_is_redacted_in_audit_history():
    payload = {
        "message_id": "pii-message",
        "conversation_id": "pii-conversation",
        "user_id": "user-1",
        "text": "我的手机号是13800138000",
    }
    with make_client() as client:
        client.post(
            "/v1/webhooks/douyin",
            headers={"X-Webhook-Secret": "test-secret"},
            json=payload,
        )
        history = client.get(
            "/v1/conversations/pii-conversation", headers={"X-Admin-Key": "test-admin"}
        ).json()
        assert "13800138000" not in history[0]["incoming"]["text"]
        assert "[已脱敏]" in history[0]["incoming"]["text"]


def test_removed_platform_is_rejected():
    with make_client() as client:
        response = client.post(
            "/v1/webhooks/taobao",
            headers={"X-Webhook-Secret": "test-secret"},
            json={"message_id": "1", "conversation_id": "1", "user_id": "1", "text": "hi"},
        )
        assert response.status_code == 422
