from functools import lru_cache

from pydantic import AliasChoices, Field
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
        default="qwen3:4b",
        validation_alias=AliasChoices("MODEL_ROUTER_SIMPLE_MODEL", "FAST_LANE_MODEL"),
    )
    model_router_standard_model: str = Field(
        default="qwen3:8b",
        validation_alias=AliasChoices("MODEL_ROUTER_STANDARD_MODEL"),
    )
    model_router_complex_model: str = Field(
        default="qwen3:8b",
        validation_alias=AliasChoices("MODEL_ROUTER_COMPLEX_MODEL", "DEEP_LANE_MODEL"),
    )
    browser_agent_provider: str = Field(
        default="ollama",
        validation_alias=AliasChoices("BROWSER_AGENT_PROVIDER", "BROWSER_USE_PROVIDER"),
    )
    browser_agent_model: str = Field(
        default="qwen3-vl:4b",
        validation_alias=AliasChoices("BROWSER_AGENT_MODEL", "BROWSER_USE_MODEL"),
    )
    ollama_host: str = Field(
        default="http://127.0.0.1:11434",
        validation_alias=AliasChoices("OLLAMA_HOST"),
    )
    ollama_timeout_seconds: int = Field(
        default=120,
        validation_alias=AliasChoices("OLLAMA_TIMEOUT_SECONDS"),
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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
