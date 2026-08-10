from pathlib import Path

from app.rag import HybridKnowledgeBase
from app.rag.embeddings import HashDenseEmbedder


def make_knowledge() -> HybridKnowledgeBase:
    return HybridKnowledgeBase(Path("knowledge/sample.json"), HashDenseEmbedder())


def test_retrieves_shipping_document():
    kb = make_knowledge()
    hits = kb.search("多久发货")
    assert hits
    assert hits[0].document.id == "demo-shipping-001"
    assert hits[0].score > 0.18
    assert hits[0].retrieval_channels == ("bm25", "dense")


def test_unrelated_question_has_no_reliable_hit():
    kb = make_knowledge()
    assert kb.search("你们老板今天穿什么颜色") == []
    assert kb.search("他好") == []
    assert kb.search("天气怎么样") == []
