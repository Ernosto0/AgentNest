"""LLM provider adapters (ADR-009). Import only from ``app.ai``."""

from app.core.config import Settings
from app.integrations.llm.base import LLMMessage, LLMProvider, LLMResult, LLMUsage
from app.integrations.llm.fake import FakeLLMProvider


def build_provider(settings: Settings) -> LLMProvider:
    """The provider selected by ``LLM_PROVIDER``. There is never a silent fallback to ``fake``."""
    if settings.llm_provider == "openai":
        # Imported here so the SDK is only loaded when the real provider is configured.
        from app.integrations.llm.openai_provider import OpenAIProvider

        return OpenAIProvider(
            settings.openai_api_key.get_secret_value(),
            reasoning_effort=settings.llm_reasoning_effort,
        )
    return FakeLLMProvider()


__all__ = [
    "FakeLLMProvider",
    "LLMMessage",
    "LLMProvider",
    "LLMResult",
    "LLMUsage",
    "build_provider",
]
