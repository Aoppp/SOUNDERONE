from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def make_client() -> TestClient:
    settings = Settings(
        llm_provider="mock",
        knowledge_path=Path("knowledge/sample.json"),
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
        assert body["citations"][0]["document_id"] == "demo-shipping-001"

        history = client.get(
            "/v1/conversations/conversation-1", headers={"X-Admin-Key": "test-admin"}
        )
        assert history.status_code == 200
        assert len(history.json()) == 1


def test_webhook_handoffs_refund_request():
    payload = {
        "message_id": "msg-2",
        "conversation_id": "conversation-2",
        "user_id": "user-2",
        "text": "我要退款",
    }
    with make_client() as client:
        response = client.post(
            "/v1/webhooks/taobao",
            headers={"X-Webhook-Secret": "test-secret"},
            json=payload,
        )
        assert response.status_code == 200
        assert response.json()["decision"] == "handoff"


def test_webhook_requires_secret():
    with make_client() as client:
        response = client.post("/v1/webhooks/jd", json={})
        assert response.status_code == 401


def test_malformed_authenticated_webhook_returns_422():
    with make_client() as client:
        response = client.post(
            "/v1/webhooks/jd",
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
            "/v1/webhooks/wechat_store",
            headers={"X-Webhook-Secret": "test-secret"},
            json=payload,
        )
        history = client.get(
            "/v1/conversations/pii-conversation", headers={"X-Admin-Key": "test-admin"}
        ).json()
        assert "13800138000" not in history[0]["incoming"]["text"]
        assert "[已脱敏]" in history[0]["incoming"]["text"]
