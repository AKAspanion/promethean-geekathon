"""Shared LangChain chat model for agent graphs (weather, news, shipment).

Respects settings.llm_provider and falls back to Ollama when Anthropic
is not configured, so analysis can run without ANTHROPIC_API_KEY.
"""

from typing import Any

from app.config import settings


def get_chat_model() -> Any | None:
    """
    Return a LangChain chat model for agent graph prompts.

    - llm_provider=openai and openai_api_key set → ChatOpenAI (supports custom
      base_url for OpenAI-compatible proxies like sandlogic)
    - llm_provider=anthropic and anthropic_api_key set → ChatAnthropic
    - llm_provider=ollama or anthropic key missing → ChatOllama (local)
    - Otherwise None (callers use heuristic fallback).
    """
    provider = (settings.llm_provider or "anthropic").lower()

    if provider == "openai" and settings.openai_api_key:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=settings.openai_model or "gpt-4o-mini",
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url or None,
            temperature=0.2,
            max_tokens=1024,
        )

    if provider == "ollama":
        from langchain_ollama import ChatOllama

        base_url = settings.ollama_base_url or "http://localhost:11434"
        model = settings.ollama_model or "llama3"
        return ChatOllama(
            base_url=base_url,
            model=model,
            temperature=0.2,
            num_predict=1024,
        )

    if provider == "anthropic" and settings.anthropic_api_key:
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=settings.anthropic_model or "claude-3-5-sonnet-20241022",
            api_key=settings.anthropic_api_key,
            max_tokens=1024,
        )

    # No valid Anthropic key but provider is anthropic: use Ollama if available
    if provider == "anthropic" and not settings.anthropic_api_key:
        from langchain_ollama import ChatOllama

        base_url = settings.ollama_base_url or "http://localhost:11434"
        model = settings.ollama_model or "llama3"
        return ChatOllama(
            base_url=base_url,
            model=model,
            temperature=0.2,
            num_predict=1024,
        )

    return None
