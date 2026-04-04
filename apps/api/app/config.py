from functools import lru_cache

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "GradeAgent API"
    api_prefix: str = "/api"
    database_url: str = "sqlite:///./gradeagent.db"
    redis_url: str = "redis://localhost:6379/0"
    temporal_enabled: bool = False
    temporal_target: str = "localhost:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "gradeagent-grading"
    model_router_provider: str = Field(
        default="ollama",
        validation_alias=AliasChoices("MODEL_ROUTER_PROVIDER", "FAST_LANE_PROVIDER"),
    )
    model_router_simple_model: str = Field(
        default="qwen3.5:4b",
        validation_alias=AliasChoices("MODEL_ROUTER_SIMPLE_MODEL", "FAST_LANE_MODEL"),
    )
    model_router_standard_model: str = Field(
        default="qwen3.5:9b",
        validation_alias=AliasChoices("MODEL_ROUTER_STANDARD_MODEL"),
    )
    model_router_complex_model: str = Field(
        default="qwen3.5:9b",
        validation_alias=AliasChoices("MODEL_ROUTER_COMPLEX_MODEL", "DEEP_LANE_MODEL"),
    )
    browser_agent_provider: str = Field(
        default="ollama",
        validation_alias=AliasChoices("BROWSER_AGENT_PROVIDER", "BROWSER_USE_PROVIDER"),
    )
    browser_agent_model: str = Field(
        default="qwen3.5:9b",
        validation_alias=AliasChoices("BROWSER_AGENT_MODEL", "BROWSER_USE_MODEL"),
    )
    browser_agent_use_vision: bool = Field(
        default=False,
        validation_alias=AliasChoices("BROWSER_AGENT_USE_VISION"),
    )
    browser_agent_force_vision: bool = Field(
        default=False,
        validation_alias=AliasChoices("BROWSER_AGENT_FORCE_VISION"),
    )
    browser_agent_visual_model: str = Field(
        default="qwen3-vl:4b",
        validation_alias=AliasChoices("BROWSER_AGENT_VISUAL_MODEL"),
    )
    browser_visual_backend: str = Field(
        default="ollama",
        validation_alias=AliasChoices("BROWSER_VISUAL_BACKEND"),
    )
    browser_visual_model: str = Field(
        default="mlx-community/Qwen2-VL-2B-Instruct-4bit",
        validation_alias=AliasChoices("BROWSER_VISUAL_MODEL"),
    )
    browser_visual_max_image_side: int = Field(
        default=768,
        validation_alias=AliasChoices("BROWSER_VISUAL_MAX_IMAGE_SIDE"),
    )
    browser_visual_max_tokens: int = Field(
        default=96,
        validation_alias=AliasChoices("BROWSER_VISUAL_MAX_TOKENS"),
    )
    ollama_host: str = Field(
        default="http://127.0.0.1:11434",
        validation_alias=AliasChoices("OLLAMA_HOST"),
    )
    ollama_timeout_seconds: int = Field(
        default=120,
        validation_alias=AliasChoices("OLLAMA_TIMEOUT_SECONDS"),
    )
    ollama_keep_alive: str = Field(
        default="15m",
        validation_alias=AliasChoices("OLLAMA_KEEP_ALIVE"),
    )
    ollama_grading_num_ctx: int = Field(
        default=6144,
        validation_alias=AliasChoices("OLLAMA_GRADING_NUM_CTX"),
    )
    ollama_grading_num_predict: int = Field(
        default=512,
        validation_alias=AliasChoices("OLLAMA_GRADING_NUM_PREDICT"),
    )
    ollama_browser_num_ctx: int = Field(
        default=8192,
        validation_alias=AliasChoices("OLLAMA_BROWSER_NUM_CTX"),
    )
    ollama_browser_num_predict: int = Field(
        default=192,
        validation_alias=AliasChoices("OLLAMA_BROWSER_NUM_PREDICT"),
    )
    ollama_simple_reasoning_mode: str = Field(
        default="off",
        validation_alias=AliasChoices("OLLAMA_SIMPLE_REASONING_MODE"),
    )
    ollama_standard_reasoning_mode: str = Field(
        default="off",
        validation_alias=AliasChoices("OLLAMA_STANDARD_REASONING_MODE"),
    )
    ollama_complex_reasoning_mode: str = Field(
        default="high",
        validation_alias=AliasChoices("OLLAMA_COMPLEX_REASONING_MODE"),
    )
    browser_agent_flash_mode: bool = Field(
        default=True,
        validation_alias=AliasChoices("BROWSER_AGENT_FLASH_MODE"),
    )
    browser_agent_use_thinking: bool = Field(
        default=False,
        validation_alias=AliasChoices("BROWSER_AGENT_USE_THINKING"),
    )
    browser_agent_max_actions_per_step: int = Field(
        default=1,
        validation_alias=AliasChoices("BROWSER_AGENT_MAX_ACTIONS_PER_STEP"),
    )
    browser_agent_max_history_items: int | None = Field(
        default=3,
        validation_alias=AliasChoices("BROWSER_AGENT_MAX_HISTORY_ITEMS"),
    )
    browser_agent_vision_detail_level: str = Field(
        default="low",
        validation_alias=AliasChoices("BROWSER_AGENT_VISION_DETAIL_LEVEL"),
    )
    browser_agent_llm_timeout_seconds: int = Field(
        default=90,
        validation_alias=AliasChoices("BROWSER_AGENT_LLM_TIMEOUT_SECONDS"),
    )
    google_api_free_tier_only: bool = Field(
        default=True,
        validation_alias=AliasChoices("GOOGLE_API_FREE_TIER_ONLY"),
    )
    google_api_free_tier_fallback_model: str = Field(
        default="gemini-3-flash-preview",
        validation_alias=AliasChoices("GOOGLE_API_FREE_TIER_FALLBACK_MODEL"),
    )
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    google_api_key: str | None = None
    browser_headless: bool = False
    browser_debug_port: int = 9222
    browser_attach_to_existing_chrome: bool = Field(
        default=False,
        validation_alias=AliasChoices("BROWSER_ATTACH_TO_EXISTING_CHROME"),
    )
    browser_existing_chrome_cdp_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("BROWSER_EXISTING_CHROME_CDP_URL"),
    )
    browser_use_system_chrome: bool = Field(
        default=False,
        validation_alias=AliasChoices("BROWSER_USE_SYSTEM_CHROME", "BROWSER_SYSTEM_CHROME"),
    )
    browser_enable_default_extensions: bool = Field(
        default=False,
        validation_alias=AliasChoices("BROWSER_ENABLE_DEFAULT_EXTENSIONS"),
    )
    browser_direct_persistent_profile: bool = Field(
        default=True,
        validation_alias=AliasChoices("BROWSER_DIRECT_PERSISTENT_PROFILE"),
    )
    browser_chrome_profile_directory: str | None = Field(
        default=None,
        validation_alias=AliasChoices("BROWSER_CHROME_PROFILE_DIRECTORY", "BROWSER_PROFILE_DIRECTORY"),
    )
    browser_persistent_profile_dir: str | None = Field(
        default="artifacts/browser/browser-use-user-data-dir-gradeagent",
        validation_alias=AliasChoices("BROWSER_PERSISTENT_PROFILE_DIR", "BROWSER_USER_DATA_DIR"),
    )
    browser_start_url: str = Field(
        default="https://www.sanomapro.fi/auth/login/",
        validation_alias=AliasChoices("BROWSER_START_URL"),
    )
    browser_cleanup_stale_after_seconds: int = Field(
        default=3600,
        validation_alias=AliasChoices("BROWSER_CLEANUP_STALE_AFTER_SECONDS"),
    )
    browser_max_saved_screenshots: int = Field(
        default=3,
        validation_alias=AliasChoices("BROWSER_MAX_SAVED_SCREENSHOTS"),
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("ollama_timeout_seconds", "browser_agent_llm_timeout_seconds", mode="before")
    @classmethod
    def _clamp_timeout_seconds(cls, value: int | str) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return 90
        return max(parsed, 30)

    @field_validator("ollama_grading_num_ctx", mode="before")
    @classmethod
    def _clamp_grading_context(cls, value: int | str) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return 6144
        return max(parsed, 2048)

    @field_validator("ollama_browser_num_ctx", mode="before")
    @classmethod
    def _clamp_browser_context(cls, value: int | str) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return 8192
        return max(parsed, 4096)

    @field_validator("ollama_browser_num_predict", "browser_visual_max_tokens", mode="before")
    @classmethod
    def _clamp_browser_predict_tokens(cls, value: int | str) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return 192
        return min(max(parsed, 32), 512)

    @field_validator("browser_agent_max_actions_per_step", mode="before")
    @classmethod
    def _clamp_browser_actions(cls, value: int | str) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return 2
        return min(max(parsed, 1), 5)

    @field_validator("browser_agent_max_history_items", mode="before")
    @classmethod
    def _clamp_browser_history(cls, value: int | str | None) -> int | None:
        if value is None:
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return 6
        if parsed <= 0:
            return None
        if parsed <= 1:
            return 2
        return parsed

    @field_validator("browser_cleanup_stale_after_seconds", mode="before")
    @classmethod
    def _clamp_cleanup_age(cls, value: int | str) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return 3600
        return max(parsed, 0)

    @field_validator("browser_max_saved_screenshots", mode="before")
    @classmethod
    def _clamp_screenshot_limit(cls, value: int | str) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return 3
        return max(parsed, 0)

    @field_validator("browser_agent_vision_detail_level", mode="before")
    @classmethod
    def _normalize_vision_detail_level(cls, value: str | None) -> str:
        if not value:
            return "low"
        normalized = str(value).strip().lower()
        if normalized not in {"auto", "low", "high"}:
            return "low"
        return normalized

    @field_validator("browser_visual_backend", mode="before")
    @classmethod
    def _normalize_visual_backend(cls, value: str | None) -> str:
        if not value:
            return "auto"
        normalized = str(value).strip().lower()
        if normalized not in {"auto", "ollama", "mlx_vlm", "off"}:
            return "auto"
        return normalized

    @field_validator("browser_visual_max_image_side", mode="before")
    @classmethod
    def _clamp_visual_image_side(cls, value: int | str) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return 768
        return min(max(parsed, 256), 1600)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
