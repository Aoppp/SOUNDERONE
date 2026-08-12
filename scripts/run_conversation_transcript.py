"""Run the conversational cases from TEST_CASES.md and export full transcripts."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from app.config import Settings
from app.main import create_app
from app.models import IncomingMessage, Platform


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_JSON = ROOT / "test_results" / "conversation_results_2026-08-12.json"
OUTPUT_MD = ROOT / "TEST_CONVERSATION_REPORT_2026-08-12.md"


@dataclass(frozen=True)
class Scenario:
    case_id: str
    turns: tuple[str, ...]
    expected: str | None = None
    note: str = ""
    separate_conversations: bool = False


def single(prefix: str, rows: Iterable[tuple]) -> list[Scenario]:
    result = []
    for row in rows:
        number, text, *rest = row
        result.append(
            Scenario(f"{prefix}-{number:03d}", (text,), rest[0] if rest else None)
        )
    return result


SCENARIOS = [
    *single("P0", [
        (1, "转人工", "handoff"),
        (2, "不要机器人，我要人工服务", "handoff"),
        (3, "我现在很不满意！", "handoff"),
        (4, "用了以后红肿刺痛怎么办", "handoff"),
        (5, "怀孕了可以用5%传明酸吗", "handoff"),
        (6, "我要退款", "handoff"),
        (7, "b5洗发水，b5含量百分之多少呢", "answered"),
        (8, "为什么没装满", "answered"),
        (9, "天气怎么样", "safe_fallback"),
        (10, "他好", "safe_fallback"),
        (11, "有去黑头产品推荐吗", "handoff"),
        (12, "有什么美白产品推荐？", "answered"),
    ]),
    Scenario("P0-013", ("美白推荐", "还有其他的吗", "这些都可以美白吗"), "answered"),
    Scenario("P0-014", ("5%传明酸是什么？", "这个怎么使用？"), "answered"),
    Scenario("P0-015", ("B5洗发水是什么香型",), "answered", "以正常产品问题代替文档中的任意输入"),
    *single("SAFE", [
        (1, "人工", "handoff"), (2, "人工服务", "handoff"),
        (3, "请帮我转人工", "handoff"), (4, "我想找真人客服", "handoff"),
        (5, "别用机器人回复我", "handoff"), (6, "转，人！工", "handoff"),
    ]),
    *single("EMO", [
        (1, "我很不满意", "handoff"), (2, "这次购物体验非常失望", "handoff"),
        (3, "你们这个处理真的太离谱了！！", "handoff"), (4, "我现在很生气，给我一个说法", "handoff"),
        (5, "这是什么态度？", "handoff"), (6, "一直不处理，没人管吗", "handoff"),
        (7, "这家店太糟糕了", "handoff"), (8, "我对这款产品的满意度调查很感兴趣", "not_handoff"),
        (9, "这款产品的满意度怎么样", "not_handoff"),
    ]),
    *single("RISK", [
        (1, "用后过敏了", "handoff"), (2, "脸上灼热发痒", "handoff"),
        (3, "用完爆痘脱皮", "handoff"), (4, "孕妇可以用吗", "handoff"),
        (5, "哺乳期能用吗", "handoff"), (6, "做完光电项目怎么用", "handoff"),
        (7, "我要退货退款", "handoff"), (8, "少发了，给我补发", "handoff"),
        (9, "我要找市场监管投诉", "handoff"), (10, "我要找媒体曝光", "handoff"),
        (11, "我手机号是13800138000", "handoff"), (12, "我要退款，不要机器人", "handoff"),
    ]),
    *single("ROUTE", [
        (1, "你好", "answered"), (2, "hello", "answered"), (3, "在吗", "answered"),
        (4, "你好，B5含量是多少", "answered"), (5, "天气怎么样", "safe_fallback"),
        (6, "你会写Python吗", "safe_fallback"), (7, "随便说说", "safe_fallback"),
        (8, "……", "safe_fallback"), (9, "怎么用", "safe_fallback"),
        (10, "这个适合我吗", "safe_fallback"), (11, "有什么抗衰产品推荐", "answered"),
        (12, "容量", "answered"),
    ]),
    *single("FAQ", [
        (1, "b5洗发水的b5含量是多少", "answered"), (2, "B5洗发水是什么香型", "answered"),
        (3, "为什么没装满", "answered"), (4, "容量", "answered"),
        (5, "为什么没装满/容量", "answered"),
        (6, "双a醇眼霜瓶子上的0.4%指的是什么", "answered"),
        (7, "EUK是什么颜色", "answered"), (8, "什么时候有货", "answered"),
        (9, "AM质地为什么这么稀", "answered"), (10, "为什么头发洗完还是油", "answered"),
    ]),
    *single("PROD", [
        (1, "5%传明酸怎么使用", "answered"), (2, "10%传明酸怎么用", "answered"),
        (3, "夜猫子精华怎么用", "answered"), (4, "玻色因面霜有什么功效", "answered"),
        (5, "麦角硫因精华浓度是多少", "answered"),
        (6, "5%传明酸可以和A醇一起用吗", "answered"),
        (7, "VCIP怎么用", "handoff"), (8, "木洗发水和火洗发水怎么搭配", "answered"),
        (9, "5%和10%传明酸有什么区别", "answered"),
        (10, "夜猫子精华能治疗暗黄吗", None),
    ]),
    *single("REC", [
        (1, "有什么美白产品推荐", "answered"), (2, "有什么抗衰产品推荐", "answered"),
        (3, "油皮适合什么抗氧化产品", "answered"), (4, "敏感肌有什么适合的产品", None),
        (5, "有去黑头产品推荐吗", "handoff"), (6, "随便推荐一款产品", None),
    ]),
    *single("SYN", [
        (1, "5%和10%传明酸有什么区别", "answered"),
        (2, "5%传明酸可以和A醇一起用吗", "answered"),
        (3, "10%传明酸可以和油橄榄、杏仁酸一起用吗", "answered"),
        (4, "麦角硫因和EUK-134怎么选", "answered"),
        (5, "这几款哪个更适合油皮", "safe_fallback"),
    ]),
    Scenario("CTX-001", ("5%传明酸是什么", "这个怎么用"), "answered"),
    Scenario("CTX-002", ("推荐美白产品", "还有其他的吗"), "answered"),
    Scenario("CTX-003", ("推荐美白产品", "还有其他的吗", "这些都可以美白吗"), "answered"),
    Scenario("CTX-004", ("推荐抗衰产品", "还有别的吗", "它们都适合油皮吗"), "answered"),
    Scenario("CTX-005", ("推荐美白产品", "那有没有抗衰的呢"), "answered"),
    Scenario("CTX-006", ("5%传明酸是什么", "他好"), None),
    Scenario("CTX-007", ("你好", "这个怎么用"), None),
    Scenario("CTX-008", ("B5洗发水是什么香型", "那它的含量是多少"), "answered"),
    Scenario("CTX-009", ("容量", "今天天气怎么样"), None),
    Scenario("CTX-010", ("5%传明酸是什么", "这个怎么用"), None, "两轮故意使用不同conversation_id", True),
    *single("FALL", [
        (1, "多久发货", "handoff"), (2, "VCIP怎么用", "handoff"),
        (3, "这款能治好痘痘吗", "handoff"),
    ]),
]


def verdict(expected: str | None, decisions: list[str]) -> str:
    if expected is None:
        return "人工复核"
    if expected == "not_handoff":
        return "通过" if all(item != "handoff" for item in decisions) else "失败"
    return "通过" if all(item == expected for item in decisions) else "失败"


def citation_text(citations: list[dict]) -> str:
    if not citations:
        return "无"
    chunks = []
    for item in citations:
        source = item.get("source_sheet") or item.get("source") or "未知来源"
        row = item.get("source_row")
        location = f"{source}!{row}" if row else source
        chunks.append(
            f"{item.get('knowledge_type', '?')} / {location} / "
            f"score={item.get('score', 0):.4f} / channels={','.join(item.get('retrieval_channels', []))}"
        )
    return "<br>".join(chunks)


async def run() -> list[dict]:
    settings = Settings(qdrant_path=None, qdrant_url=None)
    app = create_app(settings)
    results = []
    async with app.router.lifespan_context(app):
        for scenario in SCENARIOS:
            turns = []
            for index, text in enumerate(scenario.turns, start=1):
                conversation_id = (
                    f"transcript-{scenario.case_id}-{index}"
                    if scenario.separate_conversations
                    else f"transcript-{scenario.case_id}"
                )
                incoming = IncomingMessage(
                    platform=Platform.simulator,
                    external_message_id=f"transcript-{scenario.case_id}-{index}",
                    external_conversation_id=conversation_id,
                    external_user_id="automated-transcript-user",
                    text=text,
                )
                reply = await app.state.agent.handle(incoming)
                turns.append(
                    {
                        "turn": index,
                        "user": text,
                        "assistant": reply.text,
                        "decision": reply.decision.value,
                        "handoff_reason": reply.handoff_reason,
                        "risk_tags": reply.risk_tags,
                        "graph_trace": reply.graph_trace,
                        "citations": [item.model_dump() for item in reply.citations],
                    }
                )
            decisions = [item["decision"] for item in turns]
            results.append(
                {
                    "case_id": scenario.case_id,
                    "expected_decision": scenario.expected,
                    "verdict": verdict(scenario.expected, decisions),
                    "note": scenario.note,
                    "turns": turns,
                }
            )
    return results


def markdown(results: list[dict], settings: Settings) -> str:
    passed = sum(item["verdict"] == "通过" for item in results)
    failed = sum(item["verdict"] == "失败" for item in results)
    review = sum(item["verdict"] == "人工复核" for item in results)
    lines = [
        "# SOUNDERONE 对话测试逐条结果",
        "",
        f"> 生成时间：{datetime.now().astimezone().isoformat(timespec='seconds')}  ",
        f"> 运行模型：{settings.llm_provider} / {settings.deepseek_model}  ",
        "> 说明：以下是 Agent 实际完整回复，不是预期文案。",
        "",
        "## 汇总",
        "",
        f"- 对话场景：{len(results)} 组；实际消息：{sum(len(x['turns']) for x in results)} 条。",
        f"- 仅按自动化决策断言：{passed} 通过、{failed} 失败、{review} 需人工语义复核。",
        "- `人工复核` 不代表失败，只表示该用例不能仅凭 decision 判断回复内容是否合格。",
        "- 完整机器可读结果见 `test_results/conversation_results_2026-08-12.json`。",
        "",
    ]
    current_prefix = None
    for result in results:
        prefix = result["case_id"].split("-")[0]
        if prefix != current_prefix:
            lines.extend([f"## {prefix} 用例", ""])
            current_prefix = prefix
        lines.extend(
            [
                f"### {result['case_id']} — {result['verdict']}",
                "",
            ]
        )
        if result["note"]:
            lines.extend([f"备注：{result['note']}", ""])
        for turn in result["turns"]:
            lines.extend(
                [
                    f"**第 {turn['turn']} 轮用户：** {turn['user']}",
                    "",
                    f"**客服实际回复：** {turn['assistant']}",
                    "",
                    f"- decision：`{turn['decision']}`",
                    f"- handoff_reason：`{turn['handoff_reason'] or '无'}`",
                    f"- risk_tags：`{', '.join(turn['risk_tags']) or '无'}`",
                    f"- graph_trace：`{' -> '.join(turn['graph_trace'])}`",
                    f"- citations：{citation_text(turn['citations'])}",
                    "",
                ]
            )
    return "\n".join(lines)


async def main() -> None:
    settings = Settings(qdrant_path=None, qdrant_url=None)
    results = await run()
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    OUTPUT_MD.write_text(markdown(results, settings), encoding="utf-8")
    print(
        json.dumps(
            {
                "scenarios": len(results),
                "messages": sum(len(item["turns"]) for item in results),
                "passed": sum(item["verdict"] == "通过" for item in results),
                "failed": sum(item["verdict"] == "失败" for item in results),
                "manual_review": sum(item["verdict"] == "人工复核" for item in results),
                "report": str(OUTPUT_MD),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
