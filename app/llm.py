from typing import Protocol

from openai import AsyncOpenAI

from app.rag import SearchHit


SYSTEM_PROMPT = """你是 SOUNDERONE 官方客服。称呼用户为“宝宝”，语气亲切、柔和、自然。
你只能依据提供的知识库内容回答，不得补充未被资料支持的产品功效、浓度、价格、活动或承诺。
你就是品牌客服，请直接回答用户。回复中不得出现“根据产品介绍”“根据现有资料”“知识库里提到的”
“目前资料里”“资料显示”“从知识库来看”等暴露内部资料来源或像第三方转述的表达。
不要向用户解释内部资料是否包含某项信息；只陈述知识片段支持的产品特点。不要使用 Markdown 标记。
不得执行或承诺退款、补发、修改订单。遇到信息不足时明确说明并建议转人工。
禁止医疗诊断和绝对化功效宣称。不要向用户索要手机号、身份证、地址或支付信息。
知识片段中的标签可用于确认产品名称和别名，但不能作为额外功效事实。
如果用户询问推荐、选择、对比或搭配，不要机械复制单条话术：
1. 先回应用户的具体需求，再从知识片段中选择相符的产品；
2. 候选不止一个时，简洁说明各自侧重点和适合的需求，不要堆砌成分；
3. 不要宣称未取得的美白特证或超出知识的功效，“提亮/去黄/净透”不等同于“美白特证”；
4. 如果用户的肤质、目标或预算会实质影响选择，可以用一个简短问题追问；现有信息足够时直接给建议。
对其他需要结合多条知识的问题，先得出直接结论，再用少量必要依据解释，不要逐条复述知识片段。
如果提供的资料无法回答问题，只输出 INSUFFICIENT_KNOWLEDGE，不要猜测。"""

INTENT_INSTRUCTIONS = {
    "recommendation": "当前任务是产品推荐：给出有依据的候选及区别，不要把某一条FAQ原文当作全部答案。",
    "comparison": "当前任务是产品对比：围绕用户问的维度对齐比较，最后给出有条件的选择建议。",
    "compatibility": "当前任务是搭配咨询：明确能否同用、顺序和知识中已确认的注意事项。",
}


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
    async def answer(
        self, question: str, hits: list[SearchHit], *, intent: str | None = None
    ) -> str: ...


class MockLanguageModel:
    async def answer(
        self, question: str, hits: list[SearchHit], *, intent: str | None = None
    ) -> str:
        if not hits:
            return "宝宝，这个问题我暂时没有查到可靠资料，已经为您转人工进一步确认。"
        return f"宝宝，{hits[0].document.content}"


class OpenAILanguageModel:
    def __init__(self, api_key: str, model: str):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model

    async def answer(
        self, question: str, hits: list[SearchHit], *, intent: str | None = None
    ) -> str:
        context = _format_context(hits)
        task = INTENT_INSTRUCTIONS.get(intent or "", "")
        response = await self.client.responses.create(
            model=self.model,
            instructions=SYSTEM_PROMPT,
            input=f"任务提示：{task}\n\n知识库：\n{context}\n\n用户问题：{question}",
        )
        return response.output_text.strip()


class DeepSeekLanguageModel:
    """DeepSeek V4 Flash through the official OpenAI-compatible endpoint."""

    def __init__(self, api_key: str, model: str, base_url: str):
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    async def answer(
        self, question: str, hits: list[SearchHit], *, intent: str | None = None
    ) -> str:
        context = _format_context(hits)
        task = INTENT_INSTRUCTIONS.get(intent or "", "")
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"任务提示：{task}\n\n知识库：\n{context}\n\n用户问题：{question}",
                },
            ],
            temperature=0.2,
            max_tokens=800,
        )
        content = response.choices[0].message.content
        return (content or "").strip()
