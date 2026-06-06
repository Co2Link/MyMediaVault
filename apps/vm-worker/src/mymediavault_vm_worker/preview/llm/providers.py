"""Shared Pydantic AI and Logfire helpers."""

from __future__ import annotations

import os

import httpx
import logfire
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.retries import AsyncTenacityTransport, RetryConfig, wait_retry_after
from tenacity import retry_if_exception_type, stop_after_attempt, wait_exponential

from mymediavault_vm_worker.preview.llm.observability import configure_logfire

OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
_PYDANTIC_AI_INSTRUMENTED = False
_RETRYABLE_STATUS_CODES = frozenset({429, 502, 503, 504})


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
    provider = OpenAIProvider(api_key=api_key, http_client=_retrying_http_client())
    return OpenAIResponsesModel(model, provider=provider)


def _retrying_http_client() -> httpx.AsyncClient:
    transport = AsyncTenacityTransport(
        config=RetryConfig(
            retry=retry_if_exception_type(
                (
                    httpx.HTTPStatusError,
                    httpx.TimeoutException,
                    httpx.ConnectError,
                    httpx.ReadError,
                )
            ),
            wait=wait_retry_after(
                fallback_strategy=wait_exponential(multiplier=1, max=5),
                max_wait=5,
            ),
            stop=stop_after_attempt(2),
            reraise=True,
        ),
        validate_response=_raise_retryable_status,
    )
    return httpx.AsyncClient(transport=transport)


def _raise_retryable_status(response: httpx.Response) -> None:
    if response.status_code in _RETRYABLE_STATUS_CODES:
        response.raise_for_status()


class LLMConfigurationError(RuntimeError):
    """Raised when an LLM call is intentionally skipped by configuration."""
