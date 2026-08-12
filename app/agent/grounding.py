from __future__ import annotations

import re
from dataclasses import dataclass

from app.rag import SearchHit
from app.rag.entities import ProductEntityResolver


NUMERIC_CLAIM_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:\d+(?:\.\d+)?%|\d+(?:\.\d+)?\s*(?:滴|泵|次|分钟|小时|天|周|月|克|g|ml|毫升|倍))",
    re.IGNORECASE,
)
FACT_TERMS = (
    "控油", "舒缓", "抗氧化", "提亮", "去黄", "净透", "美白", "保湿", "补水",
    "淡纹", "抗皱", "紧致", "祛痘", "去黑头", "收缩毛孔", "敏感肌", "油皮",
    "干皮", "不粘腻", "清爽", "防晒", "早上", "晚上", "早晚",
)


@dataclass(frozen=True)
class GroundingResult:
    supported: bool
    unsupported_claims: tuple[str, ...] = ()


class DeterministicGroundingVerifier:
    """Reject generated numeric or product claims absent from retrieved evidence."""

    def __init__(self, entities: ProductEntityResolver):
        self.entities = entities

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r"\s+", "", text).lower()

    def verify(self, answer: str, question: str, hits: list[SearchHit]) -> GroundingResult:
        evidence = "\n".join(hit.document.index_text for hit in hits)
        normalized_evidence = self._normalize(evidence)
        unsupported: list[str] = []
        for claim in NUMERIC_CLAIM_RE.findall(answer):
            if self._normalize(claim) not in normalized_evidence:
                unsupported.append(claim)
        allowed_products = self.entities.entities(evidence) | self.entities.entities(question)
        answer_products = self.entities.entities(answer)
        unsupported.extend(sorted(answer_products - allowed_products))
        # Validate factual predicates per product-bearing sentence. This catches
        # a model attaching a real property to the wrong retrieved product.
        for sentence in re.split(r"[。！？!?；;\n]+", answer):
            terms = [term for term in FACT_TERMS if term in sentence]
            if not terms:
                continue
            for term in terms:
                if term not in evidence:
                    unsupported.append(term)
        return GroundingResult(not unsupported, tuple(dict.fromkeys(unsupported)))
