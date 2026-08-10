from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.config import Settings, get_settings
from app.knowledge import LocalKnowledgeBase
from app.llm import MockLanguageModel, OpenAILanguageModel
from app.policy import SafetyPolicy
from app.service import CustomerServiceAgent
from app.store import InMemoryConversationStore


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        knowledge = LocalKnowledgeBase(resolved.knowledge_path)
        policy = SafetyPolicy(
            resolved.business_timezone,
            resolved.business_hours_start,
            resolved.business_hours_end,
        )
        if resolved.llm_provider == "openai":
            if not resolved.openai_api_key:
                raise RuntimeError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
            llm = OpenAILanguageModel(resolved.openai_api_key, resolved.openai_model)
        else:
            llm = MockLanguageModel()
        store = InMemoryConversationStore()
        app.state.settings = resolved
        app.state.knowledge = knowledge
        app.state.store = store
        app.state.agent = CustomerServiceAgent(resolved, knowledge, policy, llm, store)
        yield

    app = FastAPI(title="SounderOne Customer Service Agent", version="0.1.0", lifespan=lifespan)
    app.include_router(router)
    return app


app = create_app()
