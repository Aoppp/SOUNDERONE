from pathlib import Path

from app.config import get_settings
from app.rag import HybridKnowledgeBase
from app.rag.embeddings import HashDenseEmbedder, OpenAIDenseEmbedder


def main() -> None:
    settings = get_settings()
    if settings.embedding_provider == "openai":
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required when EMBEDDING_PROVIDER=openai")
        embedder = OpenAIDenseEmbedder(
            settings.openai_api_key,
            settings.embedding_model,
            settings.embedding_dimensions,
        )
    else:
        embedder = HashDenseEmbedder(settings.embedding_dimensions)

    local_path = settings.qdrant_path
    if not settings.qdrant_url and local_path is None:
        local_path = Path("data/qdrant")
    knowledge = HybridKnowledgeBase(
        settings.knowledge_path,
        embedder,
        collection_name=settings.qdrant_collection,
        qdrant_url=settings.qdrant_url,
        qdrant_api_key=settings.qdrant_api_key,
        qdrant_path=local_path,
        rebuild=True,
    )
    print(
        f"indexed {len(knowledge.active_documents)} active documents "
        f"with dense + BM25 vectors into {settings.qdrant_collection}"
    )
    knowledge.close()


if __name__ == "__main__":
    main()
