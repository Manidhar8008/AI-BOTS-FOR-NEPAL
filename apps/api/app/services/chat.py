from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.vector.qdrant_client import QdrantHybridIndexer, RetrievedChunk

ChatRole = Literal["user", "assistant"]


@dataclass(frozen=True)
class ConversationTurn:
    """One UI-provided conversation turn used to preserve chat continuity."""

    role: ChatRole
    content: str


@dataclass(frozen=True)
class ChatSource:
    """Frontend-friendly citation metadata for a retrieved source."""

    source_url: str
    title: str | None
    doc_type: str
    snippet: str
    score: float
    date_scraped: str | None


@dataclass(frozen=True)
class ChatUsage:
    """Token accounting returned when the LLM provider exposes usage metadata."""

    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None


@dataclass(frozen=True)
class ChatResult:
    """Complete chat response shape used by the API route."""

    response_id: str
    tenant_id: str
    role: Literal["assistant"]
    content: str
    created_at: str
    sources: list[ChatSource]
    usage: ChatUsage


class MunicipalChatService:
    """Tenant-safe RAG orchestration for municipal chat.

    The model is explicitly forbidden from answering from its own background
    knowledge. All factual answers must come from retrieved municipal context.
    """

    def __init__(self, retriever: QdrantHybridIndexer | None = None) -> None:
        self.retriever = retriever or QdrantHybridIndexer()
        self._llm: ChatOpenAI | None = None
        self._prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    (
                        "You are a helpful municipal assistant for a government website chatbot. "
                        "Answer only from the retrieved municipal context provided to you. "
                        "Do not use outside knowledge, assumptions, or generic legal advice. "
                        "If the answer is not present in the context, say politely that you do not "
                        "have that information in the municipal knowledge base right now. "
                        "Keep answers concise, accurate, and practical. "
                        "When context supports your answer, reference the relevant source URL inline "
                        "using the exact URL text."
                    ),
                ),
                MessagesPlaceholder(variable_name="history"),
                (
                    "human",
                    (
                        "User question:\n{question}\n\n"
                        "Retrieved municipal context:\n{context}\n\n"
                        "Answer using only that context."
                    ),
                ),
            ]
        )

    async def answer(
        self,
        *,
        tenant_id: str,
        message: str,
        history: list[ConversationTurn],
        top_k: int = 5,
    ) -> ChatResult:
        """Retrieve tenant-scoped context and generate a cited assistant answer."""
        retrieved_chunks = await self.retriever.hybrid_search(
            query_text=message,
            tenant_id=tenant_id,
            limit=top_k,
        )

        if not retrieved_chunks:
            return ChatResult(
                response_id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                role="assistant",
                content=(
                    "I do not have that information in the municipal knowledge base right now."
                ),
                created_at=_utc_now().isoformat(),
                sources=[],
                usage=ChatUsage(input_tokens=None, output_tokens=None, total_tokens=None),
            )

        chain_input = {
            "history": self._history_to_langchain_messages(history),
            "question": message,
            "context": self._format_context(retrieved_chunks),
        }

        response = await self._get_llm().ainvoke(self._prompt.format_messages(**chain_input))
        content = self._message_content_to_text(response.content).strip()
        if not content:
            content = "I do not have that information in the municipal knowledge base right now."

        return ChatResult(
            response_id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            role="assistant",
            content=content,
            created_at=_utc_now().isoformat(),
            sources=self._build_sources(retrieved_chunks),
            usage=self._extract_usage(response),
        )

    def _get_llm(self) -> ChatOpenAI:
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required for chat responses.")

        if self._llm is None:
            self._llm = ChatOpenAI(
                model=settings.chat_model,
                temperature=settings.chat_temperature,
                max_tokens=settings.chat_max_tokens,
                openai_api_key=settings.openai_api_key,
            )
        return self._llm

    @staticmethod
    def _history_to_langchain_messages(history: list[ConversationTurn]) -> list[BaseMessage]:
        """Preserve recent conversation turns without trusting them as factual context."""
        messages: list[BaseMessage] = []
        for turn in history[-12:]:
            normalized_content = turn.content.strip()
            if not normalized_content:
                continue

            if turn.role == "assistant":
                messages.append(AIMessage(content=normalized_content))
            else:
                messages.append(HumanMessage(content=normalized_content))
        return messages

    @staticmethod
    def _format_context(chunks: list[RetrievedChunk]) -> str:
        """Render retrieved chunks as a readable context block for the model."""
        sections: list[str] = []
        for index, chunk in enumerate(chunks, start=1):
            title = chunk.title or "Untitled source"
            sections.append(
                (
                    f"[Context {index}]\n"
                    f"Source URL: {chunk.source_url}\n"
                    f"Document type: {chunk.doc_type}\n"
                    f"Title: {title}\n"
                    f"Content:\n{chunk.text}"
                )
            )
        return "\n\n".join(sections)

    @staticmethod
    def _build_sources(chunks: list[RetrievedChunk]) -> list[ChatSource]:
        """Return unique source URLs in ranked order for the frontend."""
        deduped: dict[str, ChatSource] = {}
        for chunk in chunks:
            if chunk.source_url in deduped:
                continue
            deduped[chunk.source_url] = ChatSource(
                source_url=chunk.source_url,
                title=chunk.title,
                doc_type=chunk.doc_type,
                snippet=chunk.text[:280].strip(),
                score=chunk.score,
                date_scraped=chunk.date_scraped,
            )
        return list(deduped.values())

    @staticmethod
    def _extract_usage(response: AIMessage) -> ChatUsage:
        """Normalize LangChain/OpenAI token usage into a stable response object."""
        usage_metadata = response.usage_metadata or {}
        input_tokens = usage_metadata.get("input_tokens")
        output_tokens = usage_metadata.get("output_tokens")
        total_tokens = usage_metadata.get("total_tokens")

        response_metadata = response.response_metadata or {}
        token_usage = response_metadata.get("token_usage") or {}
        if input_tokens is None:
            input_tokens = token_usage.get("prompt_tokens")
        if output_tokens is None:
            output_tokens = token_usage.get("completion_tokens")
        if total_tokens is None:
            total_tokens = token_usage.get("total_tokens")

        return ChatUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
        )

    @staticmethod
    def _message_content_to_text(content: object) -> str:
        """Flatten LangChain message content into plain text for the API."""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict) and "text" in item:
                    parts.append(str(item["text"]))
            return "\n".join(part for part in parts if part.strip())
        return str(content)


def _utc_now() -> datetime:
    return datetime.now(UTC)
