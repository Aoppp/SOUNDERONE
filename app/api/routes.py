import hmac
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import ValidationError

from app.adapters.generic import GenericAdapter
from app.models import Platform

router = APIRouter()


def _require_admin(request: Request, provided: str | None) -> None:
    expected = request.app.state.settings.admin_api_key
    if not hmac.compare_digest(provided or "", expected):
        raise HTTPException(status_code=401, detail="invalid admin api key")


@router.get("/health")
async def health(request: Request) -> dict[str, Any]:
    return {
        "status": "ok",
        "knowledge_documents": len(request.app.state.knowledge.documents),
        "active_knowledge_documents": len(request.app.state.knowledge.active_documents),
    }


@router.post("/v1/webhooks/{platform}")
async def webhook(
    platform: Platform,
    payload: dict[str, Any],
    request: Request,
    x_webhook_secret: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    expected = request.app.state.settings.webhook_secret
    if expected and not hmac.compare_digest(x_webhook_secret or "", expected):
        raise HTTPException(status_code=401, detail="invalid webhook secret")
    adapter = GenericAdapter(platform)
    try:
        message = adapter.parse(payload)
    except (KeyError, TypeError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail="invalid platform message payload") from exc
    reply = await request.app.state.agent.handle(message)
    return adapter.serialize(reply)


@router.post("/v1/admin/knowledge/reload")
async def reload_knowledge(
    request: Request, x_admin_key: Annotated[str | None, Header()] = None
) -> dict[str, int]:
    _require_admin(request, x_admin_key)
    return {"documents": request.app.state.knowledge.reload()}


@router.get("/v1/conversations/{conversation_id}")
async def conversation(
    conversation_id: str,
    request: Request,
    x_admin_key: Annotated[str | None, Header()] = None,
) -> list[dict[str, Any]]:
    _require_admin(request, x_admin_key)
    events = await request.app.state.store.get(conversation_id)
    return [event.model_dump(mode="json") for event in events]
