from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Faculty Analytics"

    # JWT
    secret_key: str = "CHANGE_ME_IN_PRODUCTION_USE_A_LONG_RANDOM_STRING"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 480  # 8 hours

    # Database
    database_url: str = "sqlite:///./faculty_analytics.db"

    # File storage
    uploads_dir: Path = Path("uploads")
    outputs_dir: Path = Path("outputs")

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # Gemini
    gemini_api_key: str | None = None
    # Model name lives in config because Google retires models regularly
    # (gemini-2.0-flash was shut down on 2026-06-01). Override via GEMINI_MODEL.
    gemini_model: str = "gemini-3.5-flash-lite"

    # AI provider failover chain, tried in order, e.g. "gemini,openai".
    # "basic" = rule-based only. Providers without an API key are skipped.
    ai_provider: str = "basic"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
