from datetime import datetime
from zoneinfo import ZoneInfo

from app.policy import SafetyPolicy


def make_policy() -> SafetyPolicy:
    return SafetyPolicy("Asia/Shanghai", "09:00", "22:00")


def test_adverse_reaction_forces_handoff():
    result = make_policy().evaluate_incoming("用了以后红肿刺痛怎么办")
    assert result.must_handoff is True
    assert "adverse_reaction" in result.risk_tags


def test_refund_forces_handoff():
    result = make_policy().evaluate_incoming("我要退款")
    assert result.must_handoff is True
    assert result.reason == "复杂售后需要人工处理"


def test_general_strong_negative_emotion_patterns_force_handoff():
    policy = make_policy()
    messages = (
        "我现在很不满意！",
        "这次购物体验非常失望",
        "你们这个处理真的太离谱了！！",
        "我现在很生气，给我一个说法",
        "这是什么态度？一直没人管",
    )
    for message in messages:
        result = policy.evaluate_incoming(message)
        assert result.must_handoff is True
        assert result.reason == "用户情绪激动"
        assert "strong_emotion" in result.risk_tags


def test_neutral_satisfaction_question_does_not_trigger_emotion_handoff():
    result = make_policy().evaluate_incoming("这款产品的满意度怎么样？")
    assert result.must_handoff is False


def test_phone_number_is_sensitive():
    result = make_policy().evaluate_incoming("手机号是13800138000")
    assert result.must_handoff is True
    assert "sensitive_data" in result.risk_tags


def test_output_claim_is_blocked():
    output, found = make_policy().sanitize_output("保证有效，还可以治疗问题")
    assert found == ["治疗", "保证有效"]
    assert "转接人工" in output


def test_output_guard_removes_internal_source_language():
    policy = make_policy()
    examples = (
        "宝宝，根据现有资料：建议早晚使用。",
        "宝宝，根据产品介绍，建议早晚使用。",
        "宝宝，知识库里提到的建议是早晚使用。",
        "宝宝，目前资料里显示建议早晚使用。",
        "宝宝，从知识库来看，建议早晚使用。",
    )
    for example in examples:
        output, found = policy.sanitize_output(example)
        assert output.startswith("宝宝，")
        assert "早晚使用" in output
        assert all(
            phrase not in output
            for phrase in ("根据现有资料", "根据产品介绍", "知识库", "目前资料", "资料里")
        )
        assert found == []

    output, found = policy.sanitize_output(
        "宝宝，可以考虑夜猫子精华哦～不过咱这边资料里没有直接涉及美白。"
    )
    assert output == "宝宝，可以考虑夜猫子精华哦～"
    assert found == []


def test_output_guard_removes_markdown_from_platform_copy():
    output, found = make_policy().sanitize_output("宝宝，可以看看**玻色因面霜**哦～")
    assert output == "宝宝，可以看看玻色因面霜哦～"
    assert found == []


def test_business_hours_are_timezone_aware():
    policy = make_policy()
    assert policy.is_business_hours(datetime(2026, 8, 8, 14, 0, tzinfo=ZoneInfo("Asia/Shanghai")))
    assert not policy.is_business_hours(datetime(2026, 8, 8, 23, 0, tzinfo=ZoneInfo("Asia/Shanghai")))


def test_pregnancy_and_medical_procedure_questions_force_handoff():
    policy = make_policy()
    assert policy.evaluate_incoming("孕妇可以用5%传明酸吗").must_handoff
    assert policy.evaluate_incoming("做完光电项目后怎么用").must_handoff
