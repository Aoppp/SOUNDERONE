import re
from dataclasses import dataclass, field
from datetime import datetime, time
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class PolicyResult:
    must_handoff: bool
    reason: str | None = None
    risk_tags: list[str] = field(default_factory=list)


class SafetyPolicy:
    HANDOFF_RULES = {
        "adverse_reaction": (
            "过敏",
            "红肿",
            "刺痛",
            "刺痒",
            "烂脸",
            "起疹",
            "不良反应",
            "泛红",
            "脸红",
            "灼热",
            "发痒",
            "瘙痒",
            "脱皮",
            "爆痘",
        ),
        "complex_after_sales": (
            "退款",
            "退货",
            "补发",
            "漏发",
            "少发",
            "修改订单",
            "投诉",
            "赔偿",
            "赠品未退",
            "小样未退",
            "少退回",
            "少寄回",
            "退差价",
            "扣款",
            "价保",
        ),
        "legal_or_media": ("律师", "起诉", "媒体", "曝光", "市场监管", "消协"),
        "strong_emotion": ("骗子", "垃圾", "气死", "太差", "必须解决", "再也不买"),
        "sensitive_population": ("孕妇", "孕妈妈", "孕妈", "怀孕", "孕期", "哺乳期"),
        "medical_procedure": ("医美", "光电项目", "破皮项目", "面部创口"),
    }
    FORBIDDEN_CLAIMS = ("治疗", "治愈", "抗炎", "消炎", "药到病除", "永久", "百分百", "保证有效")
    SENSITIVE_DATA = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)|\b\d{15,18}[0-9Xx]\b")
    INTERNAL_SOURCE_PATTERNS = (
        re.compile(
            r"(?:根据|按照)(?:SOUNDERONE)?(?:的)?(?:产品介绍|现有资料|目前资料|相关资料|官方资料)[，,：:\s]*",
            re.IGNORECASE,
        ),
        re.compile(
            r"(?:从)?(?:知识库|资料)(?:里|中)?(?:提到|显示|说明|介绍)(?:的|了)?[，,：:\s]*"
        ),
        re.compile(r"(?:据)?(?:现有|目前)?资料(?:里|中)?(?:提到|显示|说明|介绍)[，,：:\s]*"),
        re.compile(r"从知识库来看[，,：:\s]*"),
    )

    def __init__(self, timezone: str, start: str, end: str):
        self.timezone = ZoneInfo(timezone)
        self.start = time.fromisoformat(start)
        self.end = time.fromisoformat(end)

    def evaluate_incoming(self, text: str) -> PolicyResult:
        tags = [name for name, words in self.HANDOFF_RULES.items() if any(word in text for word in words)]
        if self.SENSITIVE_DATA.search(text):
            tags.append("sensitive_data")
        if tags:
            reason_map = {
                "adverse_reaction": "用户反馈疑似不良反应",
                "complex_after_sales": "复杂售后需要人工处理",
                "legal_or_media": "涉及法律、监管或舆情风险",
                "strong_emotion": "用户情绪激动",
                "sensitive_data": "消息包含敏感个人信息",
                "sensitive_population": "涉及孕期或哺乳期使用，需要人工确认",
                "medical_procedure": "涉及医美或创口场景，需要人工确认",
            }
            return PolicyResult(True, reason_map[tags[0]], tags)
        return PolicyResult(False)

    def is_business_hours(self, now: datetime | None = None) -> bool:
        local = (now or datetime.now(self.timezone)).astimezone(self.timezone).time()
        return self.start <= local <= self.end

    def sanitize_output(self, text: str) -> tuple[str, list[str]]:
        for pattern in self.INTERNAL_SOURCE_PATTERNS:
            text = pattern.sub("", text)
        text = re.sub(r"宝宝[，,]\s*[，,：:]", "宝宝，", text).strip()
        found = [word for word in self.FORBIDDEN_CLAIMS if word in text]
        if found:
            return "宝宝，这个问题需要进一步确认，我马上为您转接人工客服。", found
        return text, []

    def redact_sensitive_data(self, text: str) -> str:
        return self.SENSITIVE_DATA.sub("[已脱敏]", text)
