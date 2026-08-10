import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

from app.models import Citation


def _tokens(text: str) -> set[str]:
    normalized = text.lower()
    latin = re.findall(r"[a-z0-9]+", normalized)
    chinese = re.findall(r"[\u4e00-\u9fff]", normalized)
    bigrams = ["".join(chinese[i : i + 2]) for i in range(len(chinese) - 1)]
    return set(latin + chinese + bigrams)


@dataclass(frozen=True)
class KnowledgeDocument:
    id: str
    title: str
    content: str
    tags: tuple[str, ...]


@dataclass(frozen=True)
class SearchHit:
    document: KnowledgeDocument
    score: float

    def citation(self) -> Citation:
        return Citation(document_id=self.document.id, title=self.document.title, score=round(self.score, 4))


class LocalKnowledgeBase:
    """Deterministic local retriever for development; replaceable by pgvector."""

    def __init__(self, path: Path):
        self.path = path
        self.documents: list[KnowledgeDocument] = []
        self.reload()

    def reload(self) -> int:
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self.documents = [
            KnowledgeDocument(
                id=item["id"],
                title=item["title"],
                content=item["content"],
                tags=tuple(item.get("tags", [])),
            )
            for item in raw
        ]
        return len(self.documents)

    def search(self, query: str, limit: int = 4) -> list[SearchHit]:
        query_tokens = _tokens(query)
        if not query_tokens:
            return []
        hits: list[SearchHit] = []
        for doc in self.documents:
            title_tokens = _tokens(doc.title + " " + " ".join(doc.tags))
            body_tokens = _tokens(doc.content)
            title_overlap = len(query_tokens & title_tokens) / len(query_tokens)
            body_overlap = len(query_tokens & body_tokens) / len(query_tokens)
            coverage = len(query_tokens & (title_tokens | body_tokens)) / max(1, math.sqrt(len(query_tokens)))
            score = min(1.0, 0.55 * title_overlap + 0.35 * body_overlap + 0.10 * coverage)
            if score > 0:
                hits.append(SearchHit(document=doc, score=score))
        return sorted(hits, key=lambda hit: hit.score, reverse=True)[:limit]
