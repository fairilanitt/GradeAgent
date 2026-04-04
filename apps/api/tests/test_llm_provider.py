import pytest

from app.config import Settings
from app.schemas.api import CriterionDefinition
from app.services.llm_provider import (
    ProviderConfigurationError,
    VertexAIChatModel,
    browser_model_supports_vision,
    build_explicit_grading_chat_model,
    build_browser_use_llm,
    grading_reasoning_mode,
    normalize_provider,
    require_ollama_host,
    require_ollama_model_available,
    resolve_browser_model_name,
    resolve_google_model_name,
    resolve_provider_model_name,
    vertex_ai_thinking_level,
)
from app.services.model_router import GradeRequest, HeuristicModelRouter, ManagedModelRouter, get_model_router, resolve_routing_decision


def test_provider_aliases_are_normalized() -> None:
    assert normalize_provider("claude") == "anthropic"
    assert normalize_provider("gemini") == "google"
    assert normalize_provider("vertexai") == "vertex_ai"
    assert normalize_provider("local") == "ollama"
    assert normalize_provider("openai") == "openai"


def test_heuristic_provider_uses_heuristic_router() -> None:
    router = get_model_router(Settings())
    assert isinstance(router, HeuristicModelRouter)


def test_ollama_provider_raises_if_host_is_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODEL_ROUTER_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:11439")
    with pytest.raises(ProviderConfigurationError) as exc_info:
        require_ollama_host(Settings(), "grading")
    assert "OLLAMA_HOST" in str(exc_info.value)


def test_ollama_provider_builds_browser_llm_when_host_is_reachable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BROWSER_AGENT_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:11434")
    monkeypatch.setenv("BROWSER_AGENT_MODEL", "qwen3.5:9b")
    monkeypatch.setenv("BROWSER_AGENT_FORCE_VISION", "true")
    monkeypatch.setenv("BROWSER_AGENT_VISUAL_MODEL", "qwen3-vl:4b")

    class StubResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"models": [{"name": "qwen3-vl:4b"}]}

    monkeypatch.setattr("app.services.llm_provider.httpx.get", lambda *args, **kwargs: StubResponse())

    llm = build_browser_use_llm(Settings())

    assert llm.provider == "ollama"
    assert llm.model == "qwen3-vl:4b"


def test_browser_model_resolution_promotes_text_model_to_visual_when_forced() -> None:
    settings = Settings().model_copy(
        update={
            "browser_agent_provider": "ollama",
            "browser_agent_model": "qwen3.5:9b",
            "browser_agent_force_vision": True,
            "browser_agent_visual_model": "qwen3-vl:4b",
        }
    )

    assert resolve_browser_model_name(settings) == "qwen3-vl:4b"
    assert browser_model_supports_vision(settings.browser_agent_provider, resolve_browser_model_name(settings)) is True


def test_browser_model_resolution_keeps_text_model_when_force_vision_is_off() -> None:
    settings = Settings().model_copy(
        update={
            "browser_agent_provider": "ollama",
            "browser_agent_model": "qwen3.5:9b",
            "browser_agent_force_vision": False,
            "browser_agent_visual_model": "qwen3-vl:4b",
        }
    )

    assert resolve_browser_model_name(settings) == "qwen3.5:9b"


def test_browser_model_resolution_prefers_dedicated_visual_model_even_if_browser_model_is_also_visual() -> None:
    settings = Settings().model_copy(
        update={
            "browser_agent_provider": "ollama",
            "browser_agent_model": "qwen3-vl:8b",
            "browser_agent_force_vision": True,
            "browser_agent_visual_model": "qwen3-vl:4b",
        }
    )

    assert resolve_browser_model_name(settings) == "qwen3-vl:4b"


def test_ollama_visual_model_check_raises_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:11434")

    class StubResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"models": [{"name": "qwen3.5:9b"}]}

    monkeypatch.setattr("app.services.llm_provider.httpx.get", lambda *args, **kwargs: StubResponse())

    with pytest.raises(ProviderConfigurationError) as exc_info:
        require_ollama_model_available(Settings(), "qwen3-vl:4b", "browser automation")

    assert "ollama pull qwen3-vl:4b" in str(exc_info.value)


def test_routing_uses_lite_model_for_simple_text() -> None:
    payload = GradeRequest(
        assessment_title="Vocabulary",
        task_type="text_submission_scoring",
        is_exam=False,
        answer_text="Hej",
        language="sv",
        criteria=[
            CriterionDefinition(
                id="accuracy",
                label="Accuracy",
                description="Correct answer.",
                max_score=2,
                weight=1,
            )
        ],
        preferences={},
        exemplars=[],
    )

    settings = Settings().model_copy(update={"model_router_provider": "ollama"})
    decision = resolve_routing_decision(settings, payload)
    assert decision.routing_tier == "simple"
    assert decision.model_name == "qwen3.5:4b"


def test_routing_uses_qwen8b_for_complex_local_text() -> None:
    payload = GradeRequest(
        assessment_title="Essay",
        task_type="essay",
        is_exam=True,
        answer_text=(
            "Jag tycker att svenska studier är viktiga eftersom språket behövs i arbete, studier och vardag.\n"
            "Dessutom hjälper det elever i Finland att kommunicera med myndigheter och kunder."
        ),
        language="sv",
        criteria=[
            CriterionDefinition(
                id="content",
                label="Content",
                description="Addresses the topic clearly.",
                max_score=5,
                weight=1,
                expected_answer="Discusses why Swedish matters in Finland.",
            ),
            CriterionDefinition(
                id="clarity",
                label="Clarity",
                description="Easy to understand.",
                max_score=5,
                weight=1,
            ),
            CriterionDefinition(
                id="grammar",
                label="Grammar",
                description="Grammar is acceptable.",
                max_score=5,
                weight=1,
            ),
        ],
        preferences={"grading_guidance": "Prioritize nuance, grammar, and how well the answer fits the full prompt."},
        exemplars=[{"answer": "Exempeltext", "score": 13, "rationale": "Strong sample"}],
    )

    settings = Settings().model_copy(update={"model_router_provider": "ollama"})
    decision = resolve_routing_decision(settings, payload)
    assert decision.routing_tier == "complex"
    assert decision.model_name == "qwen3.5:9b"


def test_ollama_reasoning_modes_use_fast_simple_and_deeper_complex() -> None:
    settings = Settings().model_copy(update={"model_router_provider": "ollama"})

    assert grading_reasoning_mode(settings, "simple") is False
    assert grading_reasoning_mode(settings, "standard") is False
    assert grading_reasoning_mode(settings, "complex") == "high"


def test_settings_clamp_invalid_browser_history_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BROWSER_AGENT_MAX_HISTORY_ITEMS", "4")

    settings = Settings()

    assert settings.browser_agent_max_history_items == 4


def test_google_free_tier_remaps_pro_model_to_flash_preview() -> None:
    settings = Settings().model_copy(
        update={
            "google_api_free_tier_only": True,
            "google_api_free_tier_fallback_model": "gemini-3-flash-preview",
        }
    )

    assert resolve_google_model_name("gemini-3.1-pro-preview", settings) == "gemini-3-flash-preview"


def test_google_paid_tier_can_keep_pro_model() -> None:
    settings = Settings().model_copy(update={"google_api_free_tier_only": False})

    assert resolve_google_model_name("gemini-3.1-pro-preview", settings) == "gemini-3.1-pro-preview"


def test_vertex_ai_thinking_levels_follow_routing_tier() -> None:
    settings = Settings().model_copy(
        update={
            "vertex_ai_simple_thinking_level": "LOW",
            "vertex_ai_standard_thinking_level": "MEDIUM",
            "vertex_ai_complex_thinking_level": "HIGH",
        }
    )

    assert vertex_ai_thinking_level(settings, "simple") == "LOW"
    assert vertex_ai_thinking_level(settings, "standard") == "MEDIUM"
    assert vertex_ai_thinking_level(settings, "complex") == "HIGH"


def test_build_explicit_grading_chat_model_supports_vertex_ai() -> None:
    settings = Settings().model_copy(
        update={
            "vertex_ai_project": "gradeagent-test",
            "vertex_ai_location": "global",
        }
    )

    model = build_explicit_grading_chat_model(
        settings,
        provider="vertex_ai",
        model_name="gemini-3.1-pro-preview",
        routing_tier="standard",
    )

    assert isinstance(model, VertexAIChatModel)
    assert model.model == "gemini-3.1-pro-preview"
    assert model.project == "gradeagent-test"
    assert model.location == "global"
    assert model.thinking_level == "MEDIUM"


def test_build_explicit_grading_chat_model_supports_vertex_ai_api_key_mode() -> None:
    settings = Settings().model_copy(
        update={
            "vertex_ai_project": None,
            "vertex_ai_location": "global",
            "google_api_key": "test-key",
        }
    )

    model = build_explicit_grading_chat_model(
        settings,
        provider="vertex_ai",
        model_name="gemini-3.1-pro-preview",
        routing_tier="standard",
    )

    assert isinstance(model, VertexAIChatModel)
    assert model.api_key == "test-key"
    assert model.project is None
    assert model.location is None


def test_build_browser_use_llm_rejects_vertex_ai_provider() -> None:
    settings = Settings().model_copy(update={"browser_agent_provider": "vertex_ai"})

    with pytest.raises(ProviderConfigurationError) as exc_info:
        build_browser_use_llm(settings)

    assert "managed grading only" in str(exc_info.value)


def test_resolve_provider_model_name_keeps_gemini_25_flash_lite() -> None:
    settings = Settings().model_copy(update={"google_api_free_tier_only": True})

    provider, model_name = resolve_provider_model_name("google", "gemini-2.5-flash-lite", settings)

    assert provider == "google"
    assert model_name == "gemini-2.5-flash-lite"


def test_settings_default_sanomapro_exercise_grader_uses_vertex_ai_gemini_31_pro() -> None:
    settings = Settings()

    assert settings.sanomapro_exercise_grading_provider == "vertex_ai"
    assert settings.sanomapro_exercise_grading_model == "gemini-3.1-pro-preview"


def test_local_default_provider_uses_managed_router_when_requested() -> None:
    settings = Settings().model_copy(update={"model_router_provider": "ollama"})

    router = get_model_router(settings)

    assert isinstance(router, ManagedModelRouter)
