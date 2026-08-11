from __future__ import annotations

import hashlib


OUT_OF_SCOPE_RESPONSES = (
    "宝宝对不起，我只能回复 SOUNDERONE 品牌和相关产品的问题。如果你有产品相关的其他问题，我会尝试帮助你解答哟。",
    "宝宝抱歉呀，我目前只负责 SOUNDERONE 品牌和产品咨询。你可以问我产品成分、功效、用法或搭配问题～",
    "宝宝，这个问题不在我的服务范围内哦。我可以帮助你了解 SOUNDERONE 品牌及相关产品。",
    "宝宝不好意思，我只能解答 SOUNDERONE 品牌和产品相关问题，你可以换一个产品问题问问我呀。",
    "宝宝，我暂时只能提供 SOUNDERONE 品牌与产品咨询。产品用法、成分和搭配方面的问题都可以问我～",
    "宝宝对不起，这个问题我无法解答。我目前专门处理 SOUNDERONE 品牌和产品相关咨询。",
    "宝宝，我的服务范围是 SOUNDERONE 品牌及其产品。如果你想了解某款产品，可以告诉我产品名称哦。",
    "宝宝抱歉，我还不能回答这个领域的问题，但我可以继续帮你查询 SOUNDERONE 产品资料。",
    "宝宝，这个问题超出我的服务范围啦。关于 SOUNDERONE 品牌、产品成分和使用方法，我都可以尝试解答。",
    "宝宝不好意思，我只熟悉 SOUNDERONE 品牌和相关产品。你可以直接发送产品名称和想了解的问题～",
    "宝宝，我目前只能回答 SOUNDERONE 相关咨询，其他问题暂时无法提供可靠答案哦。",
    "宝宝对不起，我是 SOUNDERONE 产品客服，只能处理品牌和产品相关的问题。",
    "宝宝，这个问题我暂时帮不上忙。我可以帮助你了解 SOUNDERONE 产品的功效、用法与搭配。",
    "宝宝抱歉呀，我的知识范围只包含 SOUNDERONE 品牌和产品资料，请问你想了解哪款产品呢？",
    "宝宝，我只能基于 SOUNDERONE 的现有资料回答问题。欢迎继续咨询产品成分、肤质或使用顺序～",
    "宝宝对不起，当前我只支持 SOUNDERONE 品牌与产品问答，其他领域的问题暂时无法解答。",
    "宝宝，这不是 SOUNDERONE 品牌或产品相关问题，所以我无法给出可靠回答。你可以换个产品问题试试～",
    "宝宝不好意思，我的专长是 SOUNDERONE 产品咨询。告诉我产品名称，我会尽力帮你查询资料。",
    "宝宝，我目前只服务于 SOUNDERONE 品牌和相关产品咨询，这个问题需要你换个渠道了解哦。",
    "宝宝抱歉，这个问题不属于 SOUNDERONE 产品服务范围。产品选择、成分、用法和搭配都可以继续问我。",
)


def stable_out_of_scope_response(conversation_id: str, message_id: str) -> str:
    """Choose varied copy while keeping webhook retries deterministic."""
    digest = hashlib.sha256(f"{conversation_id}:{message_id}".encode()).digest()
    index = int.from_bytes(digest[:4], "big") % len(OUT_OF_SCOPE_RESPONSES)
    return OUT_OF_SCOPE_RESPONSES[index]
