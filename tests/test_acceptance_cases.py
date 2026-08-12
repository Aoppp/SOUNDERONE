from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


KNOWLEDGE_PATH = Path("knowledge/sounderone_knowledge.json")
HEADERS = {"X-Webhook-Secret": "acceptance-secret"}


def make_client() -> TestClient:
    return TestClient(
        create_app(
            Settings(
                llm_provider="mock",
                knowledge_path=KNOWLEDGE_PATH,
                qdrant_path=None,
                qdrant_url=None,
                webhook_secret="acceptance-secret",
                admin_api_key="acceptance-admin",
                business_hours_start="00:00",
                business_hours_end="23:59",
            )
        )
    )


def send(client: TestClient, case_id: str, text: str, *, conversation: str | None = None):
    return client.post(
        "/v1/webhooks/simulator",
        headers=HEADERS,
        json={
            "message_id": case_id,
            "conversation_id": conversation or case_id,
            "user_id": "acceptance-user",
            "text": text,
        },
    ).json()


@pytest.mark.parametrize(
    ("case_id", "text"),
    [
        ("SAFE-001", "人工"),
        ("SAFE-002", "人工服务"),
        ("SAFE-003", "请帮我转人工"),
        ("SAFE-004", "我想找真人客服"),
        ("SAFE-005", "别用机器人回复我"),
        ("SAFE-006", "转，人！工"),
    ],
)
def test_acceptance_explicit_handoff(case_id: str, text: str):
    with make_client() as client:
        body = send(client, case_id, text)
    assert body["decision"] == "handoff"
    assert body["text"] == "好的，这就为您转接人工～"
    assert body["handoff_reason"] == "用户主动要求转人工"
    assert body["graph_trace"] == ["safety_guard", "handoff"]


@pytest.mark.parametrize(
    ("case_id", "text"),
    [
        ("EMO-001", "我很不满意"),
        ("EMO-002", "这次购物体验非常失望"),
        ("EMO-003", "你们这个处理真的太离谱了！！"),
        ("EMO-004", "我现在很生气，给我一个说法"),
        ("EMO-005", "这是什么态度？"),
        ("EMO-006", "一直不处理，没人管吗"),
        ("EMO-007", "这家店太糟糕了"),
    ],
)
def test_acceptance_negative_emotion(case_id: str, text: str):
    with make_client() as client:
        body = send(client, case_id, text)
    assert body["decision"] == "handoff"
    assert body["handoff_reason"] == "用户情绪激动"
    assert "strong_emotion" in body["risk_tags"]
    assert body["graph_trace"] == ["safety_guard", "handoff"]


@pytest.mark.parametrize(
    ("case_id", "text", "risk_tag"),
    [
        ("RISK-001", "用后过敏了", "adverse_reaction"),
        ("RISK-002", "脸上灼热发痒", "adverse_reaction"),
        ("RISK-003", "用完爆痘脱皮", "adverse_reaction"),
        ("RISK-004", "孕妇可以用吗", "sensitive_population"),
        ("RISK-005", "哺乳期能用吗", "sensitive_population"),
        ("RISK-006", "做完光电项目怎么用", "medical_procedure"),
        ("RISK-007", "我要退货退款", "complex_after_sales"),
        ("RISK-008", "少发了，给我补发", "complex_after_sales"),
        ("RISK-009", "我要找市场监管投诉", "legal_or_media"),
        ("RISK-010", "我要找媒体曝光", "legal_or_media"),
        ("RISK-011", "我手机号是13800138000", "sensitive_data"),
    ],
)
def test_acceptance_risk_handoff(case_id: str, text: str, risk_tag: str):
    with make_client() as client:
        body = send(client, case_id, text)
    assert body["decision"] == "handoff"
    assert risk_tag in body["risk_tags"]
    assert body["graph_trace"] == ["safety_guard", "handoff"]


@pytest.mark.parametrize(
    ("case_id", "text", "decision", "node"),
    [
        ("ROUTE-001", "你好", "answered", "smalltalk_response"),
        ("ROUTE-002", "hello", "answered", "smalltalk_response"),
        ("ROUTE-003", "在吗", "answered", "smalltalk_response"),
        ("ROUTE-005", "天气怎么样", "safe_fallback", "out_of_scope_response"),
        ("ROUTE-006", "你会写Python吗", "safe_fallback", "out_of_scope_response"),
        ("ROUTE-007", "随便说说", "safe_fallback", "out_of_scope_response"),
        ("ROUTE-008", "……", "safe_fallback", "out_of_scope_response"),
        ("ROUTE-009", "怎么用", "safe_fallback", "clarify_response"),
        ("ROUTE-010", "这个适合我吗", "safe_fallback", "clarify_response"),
    ],
)
def test_acceptance_basic_routing(case_id: str, text: str, decision: str, node: str):
    with make_client() as client:
        body = send(client, case_id, text)
    assert body["decision"] == decision
    assert node in body["graph_trace"]
    assert body["citations"] == []


@pytest.mark.parametrize(
    ("case_id", "text", "expected", "source_row"),
    [
        ("FAQ-001", "b5洗发水的b5含量是多少", "0.20%", 85),
        ("FAQ-002", "B5洗发水是什么香型", "橙香", 71),
        ("FAQ-003", "为什么没装满", "空隙率", 80),
        ("FAQ-004", "容量", "净含量", 80),
        ("FAQ-005", "为什么没装满/容量", "空隙率", 80),
        ("FAQ-006", "双a醇眼霜瓶子上的0.4%指的是什么", "脂质体的添加量", 36),
        ("FAQ-007", "EUK是什么颜色", "琥珀色", 90),
        ("FAQ-008", "什么时候有货", "不定期", 13),
        ("FAQ-009", "AM质地为什么这么稀", "质地", 62),
        ("FAQ-010", "为什么头发洗完还是油", "冲洗", 69),
    ],
)
def test_acceptance_fact_faq(
    case_id: str, text: str, expected: str, source_row: int
):
    with make_client() as client:
        body = send(client, case_id, text)
    assert body["decision"] == "answered"
    assert expected in body["text"]
    assert "direct_faq_answer" in body["graph_trace"]
    assert "generate_answer" not in body["graph_trace"]
    assert body["citations"][0]["knowledge_type"] == "faq"
    assert body["citations"][0]["source_row"] == source_row


@pytest.mark.parametrize(
    ("case_id", "text"),
    [
        ("REC-001", "有什么美白产品推荐"),
        ("REC-002", "有什么抗衰产品推荐"),
        ("SYN-001", "5%和10%传明酸有什么区别"),
        ("SYN-002", "5%传明酸可以和A醇一起用吗"),
        ("SYN-003", "10%传明酸可以和油橄榄、杏仁酸一起用吗"),
        ("SYN-004", "麦角硫因和EUK-134怎么选"),
    ],
)
def test_acceptance_synthesis_routing(case_id: str, text: str):
    with make_client() as client:
        body = send(client, case_id, text)
    assert body["decision"] == "answered"
    assert "generate_answer" in body["graph_trace"]
    assert "direct_faq_answer" not in body["graph_trace"]
    assert body["citations"]


def test_acceptance_context_sequence():
    conversation = "CTX-003"
    with make_client() as client:
        first = send(client, "CTX-003-1", "推荐美白产品", conversation=conversation)
        second = send(client, "CTX-003-2", "还有其他的吗", conversation=conversation)
        third = send(client, "CTX-003-3", "这些都可以美白吗", conversation=conversation)
    assert all(body["decision"] == "answered" for body in (first, second, third))
    assert first["citations"][0]["document_id"] != second["citations"][0]["document_id"]
    assert any(
        "conversation_context" in citation["retrieval_channels"]
        for citation in third["citations"]
    )


def test_acceptance_output_language_forbidden_phrases():
    forbidden = re.compile(
        r"根据现有资料|根据产品介绍|知识库|目前资料|资料里|\*\*"
    )
    with make_client() as client:
        for index, text in enumerate(
            ("b5洗发水的b5含量是多少", "5%和10%传明酸有什么区别")
        ):
            body = send(client, f"OUT-language-{index}", text)
            assert forbidden.search(body["text"]) is None


def test_acceptance_api_idempotency_and_redaction():
    payload = {
        "message_id": "API-010",
        "conversation_id": "API-010",
        "user_id": "acceptance-user",
        "text": "你好",
    }
    with make_client() as client:
        first = client.post("/v1/webhooks/simulator", headers=HEADERS, json=payload).json()
        second = client.post("/v1/webhooks/simulator", headers=HEADERS, json=payload).json()
        assert first["reply_id"] == second["reply_id"]

        send(client, "API-014", "我手机号是13800138000", conversation="API-014")
        history = client.get(
            "/v1/conversations/API-014", headers={"X-Admin-Key": "acceptance-admin"}
        ).json()
    assert history[0]["incoming"]["text"] == "我手机号是[已脱敏]"
