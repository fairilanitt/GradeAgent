from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

import httpx
from browser_use import ChatAnthropic as BrowserUseChatAnthropic
from browser_use import ChatGoogle as BrowserUseChatGoogle
from browser_use import ChatOpenAI as BrowserUseChatOpenAI
from google import genai
from google.genai import types as genai_types
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama as LangChainChatOllama
from langchain_openai import ChatOpenAI

from app.config import Settings
from app.services.ollama_browser_llm import EfficientBrowserUseChatOllama

ProviderName = Literal["openai", "anthropic", "google", "vertex_ai", "ollama", "heuristic"]
RoutingTier = Literal["simple", "standard", "complex"]
DEFAULT_ROUTER_PROVIDER: ProviderName = "ollama"
DEFAULT_VISUAL_BROWSER_MODEL = "qwen3-vl:4b"
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
    "vertex_ai": "vertex_ai",
    "vertexai": "vertex_ai",
    "vertex": "vertex_ai",
    "google_vertex": "vertex_ai",
    "ollama": "ollama",
    "local": "ollama",
    "heuristic": "heuristic",
}

PROVIDER_ENV_VAR: dict[ProviderName, str] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GOOGLE_API_KEY",
    "vertex_ai": "VERTEX_AI_PROJECT",
    "ollama": "OLLAMA_HOST",
    "heuristic": "N/A",
}

OLLAMA_VISION_MODEL_MARKERS = (
    "vl",
    "vision",
    "gemma3",
    "llava",
    "bakllava",
    "minicpm-v",
    "moondream",
)


class ProviderConfigurationError(ValueError):
    """Raised when a provider is selected without the required credentials."""


@dataclass
class VertexAIChatModel:
    model: str
    project: str | None = None
    location: str | None = None
    thinking_level: str | None = None
    temperature: float = 0
    max_output_tokens: int = 4096
    api_key: str | None = None

    def __post_init__(self) -> None:
        client_kwargs: dict[str, Any] = {
            "vertexai": True,
        }
        if self.project:
            client_kwargs["project"] = self.project
        if self.location:
            client_kwargs["location"] = self.location
        if self.api_key:
            client_kwargs["api_key"] = self.api_key
        self._client = genai.Client(**client_kwargs)

    async def ainvoke(self, messages: Any) -> AIMessage:
        system_instruction, contents = _vertex_ai_prompt_parts(messages)
        config_kwargs: dict[str, Any] = {
            "temperature": self.temperature,
            "maxOutputTokens": self.max_output_tokens,
            "responseMimeType": "application/json",
        }
        thinking_config = _vertex_ai_thinking_config(self.thinking_level, self.model)
        if thinking_config is not None:
            config_kwargs["thinkingConfig"] = thinking_config
        if system_instruction:
            config_kwargs["systemInstruction"] = system_instruction

        response = await self._client.aio.models.generate_content(
            model=self.model,
            contents=contents or [{"role": "user", "parts": [{"text": ""}]}],
            config=genai_types.GenerateContentConfig(**config_kwargs),
        )
        return AIMessage(content=_vertex_ai_response_text(response))


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
    if provider == "vertex_ai":
        return settings.vertex_ai_project
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


def require_ollama_model_available(settings: Settings, model_name: str, purpose: str) -> str:
    host = require_ollama_host(settings, purpose)

    try:
        response = httpx.get(f"{host.rstrip('/')}/api/tags", timeout=min(settings.ollama_timeout_seconds, 5.0))
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        raise ProviderConfigurationError(
            f"Could not verify Ollama model '{model_name}' for {purpose}. Make sure Ollama is running."
        ) from exc

    available_models = {
        str(model.get("model") or model.get("name") or "").strip()
        for model in payload.get("models", [])
        if isinstance(model, dict)
    }
    if model_name not in available_models:
        raise ProviderConfigurationError(
            f"Ollama model '{model_name}' is required for {purpose}. Pull it with `ollama pull {model_name}`."
        )

    return host


def resolve_google_model_name(model_name: str, settings: Settings) -> str:
    normalized_model_name = model_name.strip()
    if not settings.google_api_free_tier_only:
        return normalized_model_name

    lowered = normalized_model_name.lower()
    if any(lowered.startswith(blocked_model) for blocked_model in GOOGLE_FREE_TIER_BLOCKED_MODELS):
        return settings.google_api_free_tier_fallback_model

    return normalized_model_name


def _normalize_vertex_ai_thinking_level(value: str) -> str | None:
    normalized = value.strip().upper()
    if normalized in {"", "NONE", "OFF"}:
        return None
    supported = {"MINIMAL", "LOW", "MEDIUM", "HIGH"}
    if normalized in supported:
        return normalized
    raise ProviderConfigurationError(
        "Unsupported Vertex AI thinking level "
        f"'{value}'. Supported values: {', '.join(sorted(supported))}, OFF."
    )


def vertex_ai_thinking_level(settings: Settings, routing_tier: RoutingTier) -> str | None:
    if routing_tier == "simple":
        return _normalize_vertex_ai_thinking_level(settings.vertex_ai_simple_thinking_level)
    if routing_tier == "standard":
        return _normalize_vertex_ai_thinking_level(settings.vertex_ai_standard_thinking_level)
    return _normalize_vertex_ai_thinking_level(settings.vertex_ai_complex_thinking_level)


def _resolve_vertex_ai_project(settings: Settings) -> str | None:
    project = (settings.vertex_ai_project or "").strip()
    return project or None


def _resolve_vertex_ai_location(settings: Settings) -> str | None:
    location = (settings.vertex_ai_location or "").strip()
    return location or "global"


def _vertex_ai_client_kwargs(settings: Settings) -> dict[str, Any]:
    api_key = (settings.google_api_key or "").strip()
    if api_key:
        return {
            "project": None,
            "location": None,
            "api_key": api_key,
        }

    project = _resolve_vertex_ai_project(settings)
    if not project:
        raise ProviderConfigurationError(
            "Vertex AI grading needs either GOOGLE_API_KEY for testing or VERTEX_AI_PROJECT/GOOGLE_CLOUD_PROJECT with ADC for production."
        )

    client_kwargs: dict[str, Any] = {
        "project": project,
        "location": _resolve_vertex_ai_location(settings),
    }
    return client_kwargs


def _vertex_ai_response_text(response: Any) -> str:
    text = getattr(response, "text", None)
    if isinstance(text, str) and text.strip():
        return text

    parsed = getattr(response, "parsed", None)
    if parsed is not None:
        if isinstance(parsed, str):
            return parsed
        return json.dumps(parsed, ensure_ascii=False)

    candidates = getattr(response, "candidates", None)
    if candidates:
        parts: list[str] = []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            for part in getattr(content, "parts", []) or []:
                maybe_text = getattr(part, "text", None)
                if isinstance(maybe_text, str) and maybe_text.strip():
                    parts.append(maybe_text)
        if parts:
            return "\n".join(parts)

    return str(response)


def _vertex_ai_message_role(message: BaseMessage) -> str:
    if isinstance(message, HumanMessage):
        return "user"
    if isinstance(message, SystemMessage):
        return "system"
    return "model"


def _vertex_ai_prompt_parts(messages: Any) -> tuple[str | None, list[dict[str, Any]]]:
    if not isinstance(messages, list):
        text = flatten_llm_content(messages)
        return None, [{"role": "user", "parts": [{"text": text}]}] if text.strip() else []

    system_parts: list[str] = []
    contents: list[dict[str, Any]] = []
    for raw_message in messages:
        if not isinstance(raw_message, BaseMessage):
            text = flatten_llm_content(raw_message)
            if text.strip():
                contents.append({"role": "user", "parts": [{"text": text}]})
            continue

        text = flatten_llm_content(raw_message.content)
        if not text.strip():
            continue
        role = _vertex_ai_message_role(raw_message)
        if role == "system":
            system_parts.append(text)
            continue
        contents.append({"role": role, "parts": [{"text": text}]})

    system_instruction = "\n\n".join(part for part in system_parts if part.strip()) or None
    return system_instruction, contents


def _vertex_ai_thinking_config(
    thinking_level: str | None,
    model_name: str,
) -> genai_types.ThinkingConfig | None:
    normalized_level = (thinking_level or "").strip().upper()
    if not normalized_level or not model_name.strip().lower().startswith("gemini-3"):
        return None
    return genai_types.ThinkingConfig(
        includeThoughts=False,
        thinkingLevel=getattr(genai_types.ThinkingLevel, normalized_level),
    )


def browser_model_supports_vision(provider: str, model_name: str) -> bool:
    normalized_provider = normalize_provider(provider)
    if normalized_provider == "ollama":
        normalized_model_name = model_name.strip().lower()
        return any(marker in normalized_model_name for marker in OLLAMA_VISION_MODEL_MARKERS)
    return True


def resolve_browser_model_name(settings: Settings) -> str:
    provider = normalize_provider(settings.browser_agent_provider)
    model_name = settings.browser_agent_model.strip() or DEFAULT_VISUAL_BROWSER_MODEL

    if provider == "google":
        model_name = resolve_google_model_name(model_name, settings)

    if provider == "ollama" and settings.browser_agent_force_vision:
        visual_model = settings.browser_agent_visual_model.strip()
        if visual_model:
            return visual_model
        if browser_model_supports_vision(provider, model_name):
            return model_name
        return DEFAULT_VISUAL_BROWSER_MODEL

    return model_name


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


def resolve_provider_model_name(provider: str, model_name: str, settings: Settings) -> tuple[ProviderName, str]:
    normalized_provider = normalize_provider(provider)
    resolved_model_name = model_name.strip()

    if normalized_provider == "google":
        resolved_model_name = resolve_google_model_name(resolved_model_name, settings)

    return normalized_provider, resolved_model_name


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

    return build_explicit_grading_chat_model(
        settings,
        provider=provider,
        model_name=model_name,
        routing_tier=routing_tier,
    )


def build_explicit_grading_chat_model(
    settings: Settings,
    *,
    provider: str,
    model_name: str,
    routing_tier: RoutingTier = "standard",
) -> BaseChatModel:
    provider_name, resolved_model_name = resolve_provider_model_name(provider, model_name, settings)

    if provider_name == "heuristic":
        raise ProviderConfigurationError("Heuristic is not a managed chat provider. Use the heuristic router instead.")

    if provider_name == "openai":
        return ChatOpenAI(
            model=resolved_model_name,
            api_key=require_provider_key(provider_name, settings, "grading"),
            temperature=0,
        )

    if provider_name == "anthropic":
        return ChatAnthropic(
            model=resolved_model_name,
            api_key=require_provider_key(provider_name, settings, "grading"),
            temperature=0,
            max_tokens=4096,
        )

    if provider_name == "ollama":
        return LangChainChatOllama(
            model=resolved_model_name,
            base_url=require_ollama_host(settings, "grading"),
            temperature=0,
            num_ctx=settings.ollama_grading_num_ctx,
            num_predict=settings.ollama_grading_num_predict,
            keep_alive=settings.ollama_keep_alive,
            reasoning=grading_reasoning_mode(settings, routing_tier),
            format="json",
        )

    if provider_name == "vertex_ai":
        client_kwargs = _vertex_ai_client_kwargs(settings)
        return VertexAIChatModel(
            model=resolved_model_name,
            project=client_kwargs["project"],
            location=client_kwargs["location"],
            api_key=client_kwargs.get("api_key"),
            thinking_level=vertex_ai_thinking_level(settings, routing_tier),
            temperature=0,
        )

    return ChatGoogleGenerativeAI(
        model=resolved_model_name,
        google_api_key=require_provider_key(provider_name, settings, "grading"),
        temperature=0,
    )


def build_browser_use_llm(settings: Settings):
    provider = normalize_provider(settings.browser_agent_provider)
    model_name = resolve_browser_model_name(settings)

    if provider == "heuristic":
        raise ProviderConfigurationError("Heuristic cannot be used for browser automation.")

    if provider == "vertex_ai":
        raise ProviderConfigurationError(
            "Vertex AI is supported for managed grading only. Keep browser automation on a local or browser-use provider."
        )

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
        host = require_ollama_model_available(settings, model_name, "browser automation")
        return EfficientBrowserUseChatOllama(
            model=model_name,
            host=host,
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
