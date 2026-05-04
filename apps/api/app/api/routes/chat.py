from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Tenant
from app.db.session import get_db_session
from app.services.chat import ChatResult, ConversationTurn, MunicipalChatService

router = APIRouter()


class ChatHistoryItem(BaseModel):
    """A single user or assistant turn sent by the frontend chat UI."""

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    """Request body for tenant-scoped municipal chat."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
                "message": "What are the required documents for property tax payment?",
                "history": [
                    {"role": "user", "content": "Hello"},
                    {"role": "assistant", "content": "How can I help you with municipal information?"},
                ],
            }
        }
    )

    tenant_id: uuid.UUID
    message: str = Field(min_length=1)
    history: list[ChatHistoryItem] = Field(default_factory=list)


class ChatMessageResponse(BaseModel):
    """Assistant message payload shaped for a modern chat UI."""

    id: str
    role: Literal["assistant"]
    content: str
    created_at: str


class ChatSourceResponse(BaseModel):
    source_url: str
    title: str | None
    doc_type: str
    snippet: str
    score: float
    date_scraped: str | None


class ChatUsageResponse(BaseModel):
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None


class ChatResponse(BaseModel):
    """Top-level API response containing the assistant message and citations."""

    tenant_id: uuid.UUID
    message: ChatMessageResponse
    sources: list[ChatSourceResponse]
    usage: ChatUsageResponse


@router.post(
    "/chat",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Answer a tenant-scoped municipal question using hybrid RAG",
)
async def chat(
    payload: ChatRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ChatResponse:
    """Run tenant-isolated retrieval and answer using only municipal context."""
    tenant = await session.scalar(select(Tenant).where(Tenant.id == payload.tenant_id))
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found.",
        )

    service = MunicipalChatService()
    try:
        result = await service.answer(
            tenant_id=str(payload.tenant_id),
            message=payload.message,
            history=[ConversationTurn(role=item.role, content=item.content) for item in payload.history],
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    return _to_chat_response(payload.tenant_id, result)


def _to_chat_response(tenant_id: uuid.UUID, result: ChatResult) -> ChatResponse:
    return ChatResponse(
        tenant_id=tenant_id,
        message=ChatMessageResponse(
            id=result.response_id,
            role=result.role,
            content=result.content,
            created_at=result.created_at,
        ),
        sources=[
            ChatSourceResponse(
                source_url=source.source_url,
                title=source.title,
                doc_type=source.doc_type,
                snippet=source.snippet,
                score=source.score,
                date_scraped=source.date_scraped,
            )
            for source in result.sources
        ],
        usage=ChatUsageResponse(
            input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
            total_tokens=result.usage.total_tokens,
        ),
    )
