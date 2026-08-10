from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient, models

from app.models import Citation
from app.rag.embeddings import DenseEmbedder, lexical_tokens


TAXONOMY_TAGS = {
    "产品",
    "成分",
    "卖点",
    "适合肤质",
    "适用人群",
    "功效",
    "使用方法",
    "用量",
    "使用顺序",
    "早晚",
    "使用禁忌",
    "不能搭配",
    "孕妇",
    "补充说明",
    "搭配",
    "产品区别",
    "产品选择",
    "护发产品",
    "使用建议",
    "洗护组合",
}


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

    @property
    def index_text(self) -> str:
        return f"{self.title}\n{' '.join(self.tags)}\n{self.content}"


@dataclass(frozen=True)
class SearchHit:
    document: KnowledgeDocument
    score: float
    retrieval_channels: tuple[str, ...]

    def citation(self) -> Citation:
        return Citation(
            document_id=self.document.id,
            title=self.document.title,
            score=round(self.score, 4),
            source_sheet=self.document.source_sheet,
            source_row=self.document.source_row,
            category=self.document.category,
            retrieval_channels=list(self.retrieval_channels),
        )


def _query_intent(query: str) -> str | None:
    if re.search(r"区别|对比|选哪个|怎么选", query):
        return "comparison"
    if re.search(r"搭配|叠加|一起用|能和|可以和|不能和|同用", query):
        return "compatibility"
    if re.search(r"怎么使用|怎么用|如何用|怎样用|使用方法|使用顺序|用量", query):
        return "usage"
    return None


def _matches_intent(document: KnowledgeDocument, intent: str | None) -> bool:
    if intent is None:
        return True
    searchable = document.index_text
    if intent == "usage":
        return document.category == "product_usage"
    if intent == "compatibility":
        return document.category in {"product_contraindication", "product_note"}
    if intent == "comparison":
        return document.category == "product_comparison" or "区别" in searchable
    return True


class HybridKnowledgeBase:
    """Qdrant-backed dense + BM25 retriever with explicit RRF fusion."""

    DENSE_VECTOR = "dense"
    BM25_VECTOR = "bm25"

    def __init__(
        self,
        path: Path,
        embedder: DenseEmbedder,
        *,
        collection_name: str = "sounderone_knowledge",
        qdrant_url: str | None = None,
        qdrant_api_key: str | None = None,
        qdrant_path: Path | None = None,
        rebuild: bool = True,
    ):
        self.path = path
        self.embedder = embedder
        self.collection_name = collection_name
        self.client = self._client(qdrant_url, qdrant_api_key, qdrant_path)
        self.documents: list[KnowledgeDocument] = []
        self.active_documents: list[KnowledgeDocument] = []
        self._documents_by_point: dict[str, KnowledgeDocument] = {}
        self._documents_by_id: dict[str, KnowledgeDocument] = {}
        self._product_aliases: set[str] = set()
        self._document_frequency: Counter[str] = Counter()
        self._average_length = 1.0
        self.reload(rebuild=rebuild)

    @staticmethod
    def _client(
        url: str | None, api_key: str | None, local_path: Path | None
    ) -> QdrantClient:
        if url:
            return QdrantClient(url=url, api_key=api_key)
        if local_path:
            local_path.parent.mkdir(parents=True, exist_ok=True)
            return QdrantClient(path=str(local_path))
        return QdrantClient(location=":memory:")

    def reload(self, *, rebuild: bool = True) -> int:
        payload: Any = json.loads(self.path.read_text(encoding="utf-8"))
        raw = payload["documents"] if isinstance(payload, dict) else payload
        self.documents = [self._parse_document(item) for item in raw]
        self.active_documents = [doc for doc in self.documents if doc.status == "active"]
        self._product_aliases = {
            tag
            for document in self.active_documents
            if document.category.startswith("product_")
            for tag in document.tags
            if 1 <= len(tag) <= 40 and tag in document.title and tag not in TAXONOMY_TAGS
        }
        self._documents_by_id = {document.id: document for document in self.active_documents}
        self._prepare_bm25()
        if rebuild or not self.client.collection_exists(self.collection_name):
            self.rebuild_index()
        else:
            self._documents_by_point = {
                str(uuid5(NAMESPACE_URL, doc.id)): doc for doc in self.active_documents
            }
        return len(self.documents)

    def identify_product(self, query: str) -> str:
        matches = [alias for alias in self._product_aliases if alias.lower() in query.lower()]
        if matches:
            return max(matches, key=len)
        query_tokens = set(lexical_tokens(query))
        query_ascii = {token for token in query_tokens if re.fullmatch(r"[a-z0-9]+", token)}
        candidates: list[tuple[int, int, str]] = []
        for alias in self._product_aliases:
            alias_tokens = set(lexical_tokens(alias))
            if query_ascii and not query_ascii.issubset(alias_tokens):
                continue
            shared_terms = {token for token in query_tokens & alias_tokens if len(token) >= 2}
            if shared_terms:
                candidates.append((len(shared_terms), -len(alias), alias))
        return max(candidates)[2] if candidates else ""

    def restore_hits(self, serialized_hits: list[dict[str, Any]]) -> list[SearchHit]:
        hits: list[SearchHit] = []
        for item in serialized_hits:
            document = self._documents_by_id.get(item["document_id"])
            if document:
                hits.append(
                    SearchHit(
                        document=document,
                        score=float(item["score"]),
                        retrieval_channels=tuple(item.get("retrieval_channels", [])),
                    )
                )
        return hits

    @staticmethod
    def _parse_document(item: dict[str, Any]) -> KnowledgeDocument:
        source = item.get("source", {})
        return KnowledgeDocument(
            id=item["id"],
            title=item["title"],
            content=item["content"],
            tags=tuple(item.get("tags", [])),
            category=item.get("category", "general"),
            status=item.get("status", "active"),
            risk_tags=tuple(item.get("risk_tags", [])),
            source_sheet=source.get("sheet"),
            source_row=source.get("row"),
        )

    def _prepare_bm25(self) -> None:
        token_lists = [lexical_tokens(document.index_text) for document in self.active_documents]
        self._document_frequency = Counter()
        for tokens in token_lists:
            self._document_frequency.update(set(tokens))
        self._average_length = (
            sum(len(tokens) for tokens in token_lists) / max(1, len(token_lists))
        )

    @staticmethod
    def _sparse_index(token: str) -> int:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=4).digest()
        return int.from_bytes(digest, "big") & 0x7FFFFFFF

    def _document_sparse_vector(self, text: str) -> models.SparseVector:
        counts = Counter(lexical_tokens(text))
        length = sum(counts.values()) or 1
        k1, b = 1.5, 0.75
        weights: dict[int, float] = {}
        for token, frequency in counts.items():
            denominator = frequency + k1 * (1 - b + b * length / self._average_length)
            weight = frequency * (k1 + 1) / denominator
            index = self._sparse_index(token)
            weights[index] = weights.get(index, 0.0) + weight
        indices = sorted(weights)
        return models.SparseVector(indices=indices, values=[weights[index] for index in indices])

    def _query_sparse_vector(self, text: str) -> models.SparseVector:
        total = max(1, len(self.active_documents))
        weights: dict[int, float] = {}
        for token in set(lexical_tokens(text)):
            frequency = self._document_frequency.get(token, 0)
            idf = math.log(1 + (total - frequency + 0.5) / (frequency + 0.5))
            index = self._sparse_index(token)
            weights[index] = weights.get(index, 0.0) + idf
        indices = sorted(weights)
        return models.SparseVector(indices=indices, values=[weights[index] for index in indices])

    def rebuild_index(self) -> None:
        if self.client.collection_exists(self.collection_name):
            self.client.delete_collection(self.collection_name)
        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config={
                self.DENSE_VECTOR: models.VectorParams(
                    size=self.embedder.dimensions,
                    distance=models.Distance.COSINE,
                )
            },
            sparse_vectors_config={self.BM25_VECTOR: models.SparseVectorParams()},
        )
        texts = [document.index_text for document in self.active_documents]
        dense_vectors = self.embedder.embed_documents(texts)
        points: list[models.PointStruct] = []
        self._documents_by_point = {}
        for document, dense in zip(self.active_documents, dense_vectors, strict=True):
            point_id = str(uuid5(NAMESPACE_URL, document.id))
            self._documents_by_point[point_id] = document
            points.append(
                models.PointStruct(
                    id=point_id,
                    vector={
                        self.DENSE_VECTOR: dense,
                        self.BM25_VECTOR: self._document_sparse_vector(document.index_text),
                    },
                    payload={"document_id": document.id, "category": document.category},
                )
            )
        for start in range(0, len(points), 64):
            self.client.upsert(
                collection_name=self.collection_name,
                points=points[start : start + 64],
                wait=True,
            )

    def search(self, query: str, limit: int = 4, prefetch_limit: int = 50) -> list[SearchHit]:
        if not lexical_tokens(query):
            return []
        dense = self.client.query_points(
            collection_name=self.collection_name,
            query=self.embedder.embed_query(query),
            using=self.DENSE_VECTOR,
            limit=prefetch_limit,
            with_payload=False,
        ).points
        sparse_query = self._query_sparse_vector(query)
        sparse = self.client.query_points(
            collection_name=self.collection_name,
            query=sparse_query,
            using=self.BM25_VECTOR,
            limit=prefetch_limit,
            with_payload=False,
        ).points

        rankings: dict[str, dict[str, int]] = {}
        for channel, results in (("dense", dense), ("bm25", sparse)):
            for rank, point in enumerate(results, 1):
                rankings.setdefault(str(point.id), {})[channel] = rank

        intent = _query_intent(query)
        query_tokens = set(lexical_tokens(query))
        required_ascii = {
            token for token in query_tokens if re.fullmatch(r"[a-z0-9]+", token)
        }
        query_weight = sum(
            math.log(1 + (len(self.active_documents) + 0.5) / (self._document_frequency.get(token, 0) + 0.5))
            for token in query_tokens
        ) or 1.0
        hits: list[SearchHit] = []
        maximum_rrf = 2 / 61
        for point_id, channel_ranks in rankings.items():
            document = self._documents_by_point.get(point_id)
            if document is None or not _matches_intent(document, intent):
                continue
            document_tokens = set(lexical_tokens(document.index_text))
            if required_ascii and not required_ascii.issubset(document_tokens):
                continue
            intersection = query_tokens & document_tokens
            meaningful_overlap = any(len(token) >= 2 for token in intersection) or len(intersection) >= 2
            if not meaningful_overlap:
                continue
            rrf = sum(1 / (60 + rank) for rank in channel_ranks.values())
            rrf_score = min(1.0, rrf / maximum_rrf)
            coverage = sum(
                math.log(
                    1
                    + (len(self.active_documents) + 0.5)
                    / (self._document_frequency.get(token, 0) + 0.5)
                )
                for token in intersection
            ) / query_weight
            normalized_score = min(1.0, 0.75 * rrf_score + 0.25 * coverage)
            hits.append(
                SearchHit(
                    document=document,
                    score=normalized_score,
                    retrieval_channels=tuple(sorted(channel_ranks)),
                )
            )
        return sorted(hits, key=lambda hit: hit.score, reverse=True)[:limit]

    def close(self) -> None:
        self.client.close()
