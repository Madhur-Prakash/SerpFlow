"""LLM adapter factory.

``LLM_PROVIDER=groq`` uses Groq; anything else (and an unset ``GROQ_API_KEY``)
uses the deterministic adapter. The resolved provider is reported in plan
provenance so a reader can always tell which one answered.
"""

from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.integrations.llm.base import (
    FRESHNESS_LEVELS,
    FRESHNESS_ORDER,
    EngineChoice,
    LLMAdapter,
    SelectionResult,
    SynthesisResult,
    freshness_max_age_seconds,
    stricter_freshness,
)
from app.integrations.llm.embedding import cosine_similarity, embed, embed_list
from app.integrations.llm.groq import GroqLLMAdapter
from app.integrations.llm.mock import MockLLMAdapter


@lru_cache(maxsize=4)
def get_llm(provider: str | None = None) -> LLMAdapter:
    chosen = (provider or settings.llm_provider).lower()
    if chosen == "groq":
        return GroqLLMAdapter()
    return MockLLMAdapter()


def reset_llm_cache() -> None:
    get_llm.cache_clear()


__all__ = [
    "FRESHNESS_LEVELS",
    "FRESHNESS_ORDER",
    "EngineChoice",
    "GroqLLMAdapter",
    "LLMAdapter",
    "MockLLMAdapter",
    "SelectionResult",
    "SynthesisResult",
    "cosine_similarity",
    "embed",
    "embed_list",
    "freshness_max_age_seconds",
    "get_llm",
    "reset_llm_cache",
    "stricter_freshness",
]
