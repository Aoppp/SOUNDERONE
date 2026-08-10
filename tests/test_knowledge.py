from pathlib import Path

from app.knowledge import LocalKnowledgeBase


def test_retrieves_shipping_document():
    kb = LocalKnowledgeBase(Path("knowledge/sample.json"))
    hits = kb.search("多久发货")
    assert hits
    assert hits[0].document.id == "demo-shipping-001"
    assert hits[0].score > 0.18


def test_unrelated_question_has_no_reliable_hit():
    kb = LocalKnowledgeBase(Path("knowledge/sample.json"))
    assert kb.search("你们老板今天穿什么颜色") == []
