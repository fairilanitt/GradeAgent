from __future__ import annotations

import json
from typing import Any, Literal

import httpx
from browser_use import ChatAnthropic as BrowserUseChatAnthropic
from browser_use import ChatGoogle as BrowserUseChatGoogle
from browser_use import ChatOpenAI as BrowserUseChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama as LangChainChatOllama
from langchain_openai import ChatOpenAI

from app.config import Settings
from app.services.ollama_browser_llm import EfficientBrowserUseChatOllama

ProviderName = Literal["openai", "anthropic", "google", "ollama", "heuristic"]
RoutingTier = Literal["simple", "standard", "complex"]
DEFAULT_ROUTER_PROVIDER: ProviderName = "ollama"
GOOGLE_FREE_TIER_BLOCKED_MODELS = (
    "gemini-3.1-pro-preview",
    "gemini-3.1-pro-preview-customtools",
    "gemini-3-pro-preview",
    "gemini-3-pro-image-preview",
)

PROVIDER_ALIASES: dict[str, ProviderName] = {
    "openai": "openai",
    "anthropic": "anthropic",
    "claude": "anthropic",
    "google": "google",
    "gemini": "google",
    "ollama": "ollama",
    "local": "ollama",
    "heuristic": "heuristic",
}

PROVIDER_ENV_VAR: dict[ProviderName, str] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GOOGLE_API_KEY",
    "ollama": "OLLAMA_HOST",
    "heuristic": "N/A",
}


class ProviderConfigurationError(ValueError):
    """Raised when a provider is selected without the required credentials."""


def normalize_provider(provider: str) -> ProviderName:
    normalized = PROVIDER_ALIASES.get(provider.strip().lower())
    if normalized is None:
        supported = ", ".join(sorted(PROVIDER_ALIASES))
        raise ProviderConfigurationError(f"Unsupported model provider '{provider}'. Supported values: {supported}.")
    return normalized


def _provider_key(provider: ProviderName, settings: Settings) -> str | None:
    if provider == "openai":
        return settings.openai_api_key
    if provider == "anthropic":
        return settings.anthropic_api_key
    if provider == "google":
        return settings.google_api_key
    if provider == "ollama":
        return settings.ollama_host
    return None


def require_provider_key(provider: ProviderName, settings: Settings, purpose: str) -> str:
    if provider == "ollama":
        return require_ollama_host(settings, purpose)
    api_key = _provider_key(provider, settings)
    if api_key:
        return api_key
    env_var = PROVIDER_ENV_VAR[provider]
    raise ProviderConfigurationError(f"{env_var} is required for {purpose} provider '{provider}'.")


def grading_provider(settings: Settings) -> ProviderName:
    return normalize_provider(settings.model_router_provider)


def require_ollama_host(settings: Settings, purpose: str) -> str:
    host = settings.ollama_host.strip()
    if not host:
        raise ProviderConfigurationError(f"OLLAMA_HOST is required for {purpose} provider 'ollama'.")

    try:
        response = httpx.get(f"{host.rstrip('/')}/api/tags", timeout=min(settings.ollama_timeout_seconds, 5.0))
        response.raise_for_status()
    except Exception as exc:
        raise ProviderConfigurationError(
            f"OLLAMA_HOST '{host}' is not reachable for {purpose}. Start Ollama with `ollama serve`."
        ) from exc
    return host


def resolve_google_model_name(model_name: str, settings: Settings) -> str:
    normalized_model_name = model_name.strip()
    if not settings.google_api_free_tier_only:
        return normalized_model_name

    lowered = normalized_model_name.lower()
    if any(lowered.startswith(blocked_model) for blocked_model in GOOGLE_FREE_TIER_BLOCKED_MODELS):
        return settings.google_api_free_tier_fallback_model

    return normalized_model_name


def grading_model_name(settings: Settings, routing_tier: RoutingTier) -> str:
    if routing_tier == "simple":
        model_name = settings.model_router_simple_model
    elif routing_tier == "standard":
        model_name = settings.model_router_standard_model
    else:
        model_name = settings.model_router_complex_model

    if grading_provider(settings) == "google":
        return resolve_google_model_name(model_name, settings)
    return model_name


def _normalize_reasoning_mode(value: str) -> bool | str:
    normalized = value.strip().lower()
    if normalized in {"", "0", "false", "none", "off"}:
        return False
    if normalized in {"1", "true", "on"}:
        return True
    return normalized


def grading_reasoning_mode(settings: Settings, routing_tier: RoutingTier) -> bool | str:
    if routing_tier == "simple":
        return _normalize_reasoning_mode(settings.ollama_simple_reasoning_mode)
    if routing_tier == "standard":
        return _normalize_reasoning_mode(settings.ollama_standard_reasoning_mode)
    return _normalize_reasoning_mode(settings.ollama_complex_reasoning_mode)


def should_use_heuristic_grading(settings: Settings) -> bool:
    return grading_provider(settings) == "heuristic"


def build_grading_chat_model(settings: Settings, routing_tier: RoutingTier) -> BaseChatModel:
    provider = grading_provider(settings)
    model_name = grading_model_name(settings, routing_tier)

    if provider == "heuristic":
        raise ProviderConfigurationError("Heuristic is not a managed chat provider. Use the heuristic router instead.")

    if provider == "openai":
        return ChatOpenAI(
            model=model_name,
            api_key=require_provider_key(provider, settings, "grading"),
            temperature=0,
        )

    if provider == "anthropic":
        return ChatAnthropic(
            model=model_name,
            api_key=require_provider_key(provider, settings, "grading"),
            temperature=0,
            max_tokens=4096,
        )

    if provider == "ollama":
        return LangChainChatOllama(
            model=model_name,
            base_url=require_ollama_host(settings, "grading"),
            temperature=0,
            num_ctx=settings.ollama_grading_num_ctx,
            num_predict=settings.ollama_grading_num_predict,
            keep_alive=settings.ollama_keep_alive,
            reasoning=grading_reasoning_mode(settings, routing_tier),
            format="json",
        )

    return ChatGoogleGenerativeAI(
        model=model_name,
        google_api_key=require_provider_key(provider, settings, "grading"),
        temperature=0,
    )


def build_browser_use_llm(settings: Settings):
    provider = normalize_provider(settings.browser_agent_provider)
    model_name = settings.browser_agent_model

    if provider == "heuristic":
        raise ProviderConfigurationError("Heuristic cannot be used for browser automation.")

    if provider == "openai":
        return BrowserUseChatOpenAI(
            model=model_name,
            api_key=require_provider_key(provider, settings, "browser automation"),
            temperature=0,
        )

    if provider == "anthropic":
        return BrowserUseChatAnthropic(
            model=model_name,
            api_key=require_provider_key(provider, settings, "browser automation"),
            temperature=0,
        )

    if provider == "ollama":
        return EfficientBrowserUseChatOllama(
            model=model_name,
            host=require_ollama_host(settings, "browser automation"),
            timeout=settings.ollama_timeout_seconds,
            keep_alive=settings.ollama_keep_alive,
            think="low" if settings.browser_agent_use_thinking else False,
            ollama_options={
                "temperature": 0,
                "num_ctx": settings.ollama_browser_num_ctx,
                "num_predict": settings.ollama_browser_num_predict,
            },
        )

    model_name = resolve_google_model_name(model_name, settings)
    return BrowserUseChatGoogle(
        model=model_name,
        api_key=require_provider_key(provider, settings, "browser automation"),
        temperature=0,
    )


def flatten_llm_content(content: Any) -> str:
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = [flatten_llm_content(item) for item in content]
        return "\n".join(part for part in parts if part.strip())

    if isinstance(content, dict):
        if isinstance(content.get("text"), str):
            return content["text"]
        if isinstance(content.get("content"), str):
            return content["content"]
        return json.dumps(content, ensure_ascii=False)

    return str(content)


def extract_json_object(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3:
            stripped = "\n".join(lines[1:-1]).strip()

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ProviderConfigurationError("Model response did not contain a JSON object.")
    return stripped[start : end + 1]
