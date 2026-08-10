from typing import Protocol

from openai import AsyncOpenAI

from app.knowledge import SearchHit


SYSTEM_PROMPT = """你是 SounderOne 官方客服。称呼用户为“宝宝”，语气亲切、柔和、简洁。
你只能依据提供的知识库内容回答，不得补充未被资料支持的产品功效、浓度、价格、活动或承诺。
不得执行或承诺退款、补发、修改订单。遇到信息不足时明确说明并建议转人工。
禁止医疗诊断和绝对化功效宣称。不要向用户索要手机号、身份证、地址或支付信息。"""


class LanguageModel(Protocol):
    async def answer(self, question: str, hits: list[SearchHit]) -> str: ...


class MockLanguageModel:
    async def answer(self, question: str, hits: list[SearchHit]) -> str:
        if not hits:
            return "宝宝，这个问题我暂时没有查到可靠资料，已经为您转人工进一步确认。"
        return f"宝宝，根据现有资料：{hits[0].document.content}"


class OpenAILanguageModel:
    def __init__(self, api_key: str, model: str):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model

    async def answer(self, question: str, hits: list[SearchHit]) -> str:
        context = "\n\n".join(f"[{hit.document.title}]\n{hit.document.content}" for hit in hits)
        response = await self.client.responses.create(
            model=self.model,
            instructions=SYSTEM_PROMPT,
            input=f"知识库：\n{context}\n\n用户问题：{question}",
        )
        return response.output_text.strip()
