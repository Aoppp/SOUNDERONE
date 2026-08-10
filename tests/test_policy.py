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


def test_phone_number_is_sensitive():
    result = make_policy().evaluate_incoming("手机号是13800138000")
    assert result.must_handoff is True
    assert "sensitive_data" in result.risk_tags


def test_output_claim_is_blocked():
    output, found = make_policy().sanitize_output("保证有效，还可以治疗问题")
    assert found == ["治疗", "保证有效"]
    assert "转接人工" in output


def test_business_hours_are_timezone_aware():
    policy = make_policy()
    assert policy.is_business_hours(datetime(2026, 8, 8, 14, 0, tzinfo=ZoneInfo("Asia/Shanghai")))
    assert not policy.is_business_hours(datetime(2026, 8, 8, 23, 0, tzinfo=ZoneInfo("Asia/Shanghai")))


def test_pregnancy_and_medical_procedure_questions_force_handoff():
    policy = make_policy()
    assert policy.evaluate_incoming("孕妇可以用5%传明酸吗").must_handoff
    assert policy.evaluate_incoming("做完光电项目后怎么用").must_handoff
