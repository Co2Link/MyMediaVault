"""Shared Pydantic AI and Logfire helpers."""

from __future__ import annotations

import os
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

import logfire

from mymediavault_vm_worker.preview.llm.observability import configure_logfire

OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
_PYDANTIC_AI_INSTRUMENTED = False


def configure_llm_observability() -> None:
    """Configure Logfire instrumentation for Pydantic AI once per process."""

    global _PYDANTIC_AI_INSTRUMENTED

    configure_logfire()

    if not _PYDANTIC_AI_INSTRUMENTED:
        logfire.instrument_pydantic_ai(
            include_content=False,
            include_binary_content=False,
        )
        _PYDANTIC_AI_INSTRUMENTED = True


def openai_responses_model(model: str) -> OpenAIResponsesModel:
    """Build an OpenAI Responses model for Pydantic AI."""

    api_key = os.getenv(OPENAI_API_KEY_ENV)
    if not api_key:
        msg = f"{OPENAI_API_KEY_ENV} is not configured"
        raise LLMConfigurationError(msg)
    provider = OpenAIProvider(api_key=api_key)
    return OpenAIResponsesModel(model, provider=provider)


class LLMConfigurationError(RuntimeError):
    """Raised when an LLM call is intentionally skipped by configuration."""
