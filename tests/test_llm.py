from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agent import SounderOneGraphAgent
from app.config import Settings
from app.llm import DeepSeekLanguageModel
from app.models import IncomingMessage, Platform
from app.policy import SafetyPolicy
from app.rag import HybridKnowledgeBase
from app.rag.embeddings import HashDenseEmbedder
from app.store import InMemoryConversationStore


@pytest.mark.asyncio
async def test_deepseek_flash_uses_grounded_chat_completion_payload():
    captured = {}

    async def create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="宝宝，测试回答"))]
        )

    model = DeepSeekLanguageModel("test-key", "deepseek-v4-flash", "https://api.deepseek.com")
    model.client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    knowledge = HybridKnowledgeBase(Path("knowledge/sample.json"), HashDenseEmbedder())
    hits = knowledge.search("多久发货")

    answer = await model.answer("多久发货", hits)

    assert answer == "宝宝，测试回答"
    assert captured["model"] == "deepseek-v4-flash"
    assert "[faq:【测试数据】发货时效]" in captured["messages"][1]["content"]
    assert "标签：发货、物流、多久发货" in captured["messages"][1]["content"]
    assert captured["temperature"] == 0.2


class InsufficientKnowledgeModel:
    async def answer(self, question, hits):
        return "INSUFFICIENT_KNOWLEDGE"


@pytest.mark.asyncio
async def test_generation_insufficient_signal_handoffs_instead_of_answering():
    settings = Settings(
        knowledge_path=Path("knowledge/sample.json"),
        qdrant_path=None,
        qdrant_url=None,
        business_hours_start="00:00",
        business_hours_end="23:59",
    )
    knowledge = HybridKnowledgeBase(Path("knowledge/sample.json"), HashDenseEmbedder())
    agent = SounderOneGraphAgent(
        settings,
        knowledge,
        SafetyPolicy("Asia/Shanghai", "00:00", "23:59"),
        InsufficientKnowledgeModel(),
        InMemoryConversationStore(),
    )
    reply = await agent.handle(
        IncomingMessage(
            platform=Platform.simulator,
            external_message_id="insufficient-1",
            external_conversation_id="insufficient-conversation",
            external_user_id="user-1",
            text="多久发货",
        )
    )
    assert reply.decision.value == "handoff"
    assert reply.handoff_reason == "知识片段不足以生成可靠答案"
    assert "generation_insufficient_knowledge" in reply.risk_tags
    assert reply.graph_trace[-1] == "handoff"
