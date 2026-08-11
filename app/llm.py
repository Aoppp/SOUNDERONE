from typing import Protocol

from openai import AsyncOpenAI

from app.rag import SearchHit


SYSTEM_PROMPT = """你是 SOUNDERONE 官方客服。称呼用户为“宝宝”，语气亲切、柔和、简洁。
你只能依据提供的知识库内容回答，不得补充未被资料支持的产品功效、浓度、价格、活动或承诺。
你就是品牌客服，请直接回答用户。回复中不得出现“根据产品介绍”“根据现有资料”“知识库里提到的”
“目前资料里”“资料显示”“从知识库来看”等暴露内部资料来源或像第三方转述的表达。
不得执行或承诺退款、补发、修改订单。遇到信息不足时明确说明并建议转人工。
禁止医疗诊断和绝对化功效宣称。不要向用户索要手机号、身份证、地址或支付信息。
知识片段中的标签可用于确认产品名称和别名，但不能作为额外功效事实。
如果提供的资料无法回答问题，只输出 INSUFFICIENT_KNOWLEDGE，不要猜测。"""


def _format_context(hits: list[SearchHit]) -> str:
    return "\n\n".join(
        "\n".join(
            (
                f"[{hit.document.knowledge_type}:{hit.document.title}]",
                f"分类：{hit.document.category}",
                f"标签：{'、'.join(hit.document.tags)}",
                f"正文：{hit.document.content}",
            )
        )
        for hit in hits
    )


class LanguageModel(Protocol):
    async def answer(self, question: str, hits: list[SearchHit]) -> str: ...


class MockLanguageModel:
    async def answer(self, question: str, hits: list[SearchHit]) -> str:
        if not hits:
            return "宝宝，这个问题我暂时没有查到可靠资料，已经为您转人工进一步确认。"
        return f"宝宝，{hits[0].document.content}"


class OpenAILanguageModel:
    def __init__(self, api_key: str, model: str):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model

    async def answer(self, question: str, hits: list[SearchHit]) -> str:
        context = _format_context(hits)
        response = await self.client.responses.create(
            model=self.model,
            instructions=SYSTEM_PROMPT,
            input=f"知识库：\n{context}\n\n用户问题：{question}",
        )
        return response.output_text.strip()


class DeepSeekLanguageModel:
    """DeepSeek V4 Flash through the official OpenAI-compatible endpoint."""

    def __init__(self, api_key: str, model: str, base_url: str):
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    async def answer(self, question: str, hits: list[SearchHit]) -> str:
        context = _format_context(hits)
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"知识库：\n{context}\n\n用户问题：{question}",
                },
            ],
            temperature=0.2,
            max_tokens=800,
        )
        content = response.choices[0].message.content
        return (content or "").strip()
