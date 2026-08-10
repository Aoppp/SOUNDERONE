import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.models import Citation


CHINESE_STOP_CHARS = set("的了呢吗啊呀哦吧和与及或是在有我你他她它们您这那个请问是否")


def _tokens(text: str) -> set[str]:
    normalized = text.lower()
    latin = re.findall(r"[a-z0-9]+", normalized)
    chinese = re.findall(r"[\u4e00-\u9fff]", normalized)
    bigrams = ["".join(chinese[i : i + 2]) for i in range(len(chinese) - 1)]
    meaningful_chars = [character for character in chinese if character not in CHINESE_STOP_CHARS]
    return set(latin + meaningful_chars + bigrams)


def _normalized_phrase(text: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", text.lower())


def _query_intent(query: str) -> str | None:
    if re.search(r"搭配|叠加|一起用|能和|可以和|不能和|同用", query):
        return "compatibility"
    if re.search(r"怎么用|如何用|怎样用|使用方法|使用顺序|用量", query):
        return "usage"
    return None


def _matches_intent(document: "KnowledgeDocument", intent: str | None) -> bool:
    if intent is None:
        return True
    searchable = document.title + "\n" + document.content
    if intent == "usage":
        return document.category == "product_usage" or bool(
            re.search(r"怎么使用|怎么用|如何用|使用方法|使用顺序|用量", searchable)
        )
    if intent == "compatibility":
        return document.category in {"product_contraindication", "product_note", "product_comparison"} or bool(
            re.search(r"搭配|叠加|一起使用|不能和|不建议和|分开使用", searchable)
        )
    return True


@dataclass(frozen=True)
class KnowledgeDocument:
    id: str
    title: str
    content: str
    tags: tuple[str, ...]
    category: str = "general"
    status: str = "active"
    risk_tags: tuple[str, ...] = ()
    source_sheet: str | None = None
    source_row: int | None = None


@dataclass(frozen=True)
class SearchHit:
    document: KnowledgeDocument
    score: float

    def citation(self) -> Citation:
        return Citation(
            document_id=self.document.id,
            title=self.document.title,
            score=round(self.score, 4),
            source_sheet=self.document.source_sheet,
            source_row=self.document.source_row,
            category=self.document.category,
        )


class LocalKnowledgeBase:
    """Deterministic local retriever for development; replaceable by pgvector."""

    def __init__(self, path: Path):
        self.path = path
        self.documents: list[KnowledgeDocument] = []
        self.active_documents: list[KnowledgeDocument] = []
        self._title_tokens: dict[str, set[str]] = {}
        self._body_tokens: dict[str, set[str]] = {}
        self._idf: dict[str, float] = {}
        self.reload()

    def reload(self) -> int:
        payload: Any = json.loads(self.path.read_text(encoding="utf-8"))
        raw = payload["documents"] if isinstance(payload, dict) else payload
        self.documents = [
            KnowledgeDocument(
                id=item["id"],
                title=item["title"],
                content=item["content"],
                tags=tuple(item.get("tags", [])),
                category=item.get("category", "general"),
                status=item.get("status", "active"),
                risk_tags=tuple(item.get("risk_tags", [])),
                source_sheet=item.get("source", {}).get("sheet"),
                source_row=item.get("source", {}).get("row"),
            )
            for item in raw
        ]
        self.active_documents = [document for document in self.documents if document.status == "active"]
        self._title_tokens = {
            document.id: _tokens(document.title + " " + " ".join(document.tags))
            for document in self.active_documents
        }
        self._body_tokens = {document.id: _tokens(document.content) for document in self.active_documents}
        frequencies: Counter[str] = Counter()
        for document in self.active_documents:
            frequencies.update(self._title_tokens[document.id] | self._body_tokens[document.id])
        document_count = max(1, len(self.active_documents))
        self._idf = {
            token: math.log((document_count + 1) / (frequency + 1)) + 1
            for token, frequency in frequencies.items()
        }
        return len(self.documents)

    def search(self, query: str, limit: int = 4) -> list[SearchHit]:
        query_tokens = _tokens(query)
        if not query_tokens:
            return []
        query_weight = sum(self._idf.get(token, 1.0) for token in query_tokens)
        query_phrase = _normalized_phrase(query)
        intent = _query_intent(query)
        required_ascii_tokens = {
            token for token in query_tokens if re.fullmatch(r"[a-z0-9]+", token)
        }
        hits: list[SearchHit] = []
        for doc in self.active_documents:
            if not _matches_intent(doc, intent):
                continue
            title_tokens = self._title_tokens[doc.id]
            body_tokens = self._body_tokens[doc.id]
            combined_tokens = title_tokens | body_tokens
            if required_ascii_tokens and not required_ascii_tokens.issubset(combined_tokens):
                continue
            intersection = query_tokens & combined_tokens
            meaningful_overlap = any(len(token) >= 2 for token in intersection) or len(intersection) >= 2
            if not meaningful_overlap:
                continue
            title_overlap = sum(self._idf.get(token, 1.0) for token in query_tokens & title_tokens) / query_weight
            body_overlap = sum(self._idf.get(token, 1.0) for token in query_tokens & body_tokens) / query_weight
            coverage = sum(self._idf.get(token, 1.0) for token in intersection) / query_weight
            searchable_phrase = _normalized_phrase(doc.title + " " + " ".join(doc.tags) + " " + doc.content)
            exact_bonus = 0.15 if len(query_phrase) >= 2 and query_phrase in searchable_phrase else 0.0
            score = min(1.0, 0.50 * title_overlap + 0.35 * body_overlap + 0.15 * coverage + exact_bonus)
            if score > 0:
                hits.append(SearchHit(document=doc, score=score))
        return sorted(hits, key=lambda hit: hit.score, reverse=True)[:limit]
