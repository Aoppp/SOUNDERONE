from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.config import Settings, get_settings
from app.agent import SounderOneGraphAgent
from app.llm import DeepSeekLanguageModel, MockLanguageModel, OpenAILanguageModel
from app.policy import SafetyPolicy
from app.rag import HybridKnowledgeBase
from app.rag.embeddings import HashDenseEmbedder, OpenAIDenseEmbedder
from app.store import InMemoryConversationStore


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if resolved.embedding_provider == "openai":
            if not resolved.openai_api_key:
                raise RuntimeError("OPENAI_API_KEY is required when EMBEDDING_PROVIDER=openai")
            embedder = OpenAIDenseEmbedder(
                resolved.openai_api_key,
                resolved.embedding_model,
                resolved.embedding_dimensions,
            )
        else:
            embedder = HashDenseEmbedder(resolved.embedding_dimensions)
        knowledge_paths = (
            [resolved.knowledge_path]
            if resolved.knowledge_path
            else [resolved.product_knowledge_path, resolved.faq_knowledge_path]
        )
        knowledge = HybridKnowledgeBase(
            knowledge_paths,
            embedder,
            collection_name=resolved.qdrant_collection,
            qdrant_url=resolved.qdrant_url,
            qdrant_api_key=resolved.qdrant_api_key,
            qdrant_path=resolved.qdrant_path,
            rebuild=resolved.rag_rebuild_on_startup,
        )
        policy = SafetyPolicy(
            resolved.business_timezone,
            resolved.business_hours_start,
            resolved.business_hours_end,
        )
        if resolved.llm_provider == "openai":
            if not resolved.openai_api_key:
                raise RuntimeError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
            llm = OpenAILanguageModel(resolved.openai_api_key, resolved.openai_model)
        elif resolved.llm_provider == "deepseek":
            if not resolved.deepseek_api_key:
                raise RuntimeError("DEEPSEEK_API_KEY is required when LLM_PROVIDER=deepseek")
            llm = DeepSeekLanguageModel(
                resolved.deepseek_api_key,
                resolved.deepseek_model,
                resolved.deepseek_base_url,
            )
        else:
            llm = MockLanguageModel()
        store = InMemoryConversationStore()
        app.state.settings = resolved
        app.state.knowledge = knowledge
        app.state.store = store
        app.state.agent = SounderOneGraphAgent(resolved, knowledge, policy, llm, store)
        yield
        knowledge.close()

    app = FastAPI(title="SounderOne Douyin Customer Service Agent", version="0.2.0", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
    app.include_router(router)
    return app


app = create_app()
