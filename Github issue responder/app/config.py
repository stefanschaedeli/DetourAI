"""Configuration management for GitHub Issue Responder."""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # GitHub
    github_token: str
    github_webhook_secret: str
    github_repo: str = "stefanschaedeli/DetourAI"

    # Claude API
    anthropic_api_key: str

    # Email (SMTP)
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    notify_email: str = "ss@nip.ch"

    # App
    app_base_url: str = "http://localhost:8000"
    app_secret_key: str = "change-me-in-production"
    log_level: str = "INFO"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
