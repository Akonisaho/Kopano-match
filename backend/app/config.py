from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


DEV_JWT_SECRET = "dev-only-secret-not-for-production-use-0000"
MIN_JWT_SECRET_BYTES = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # The app connects as kopano_app (no UPDATE/DELETE on audit). seed.py uses the admin URL.
    database_url: str = "postgresql://kopano_app:kopano_app_dev@localhost:55432/kopano"
    admin_database_url: str = "postgresql://postgres:postgres@localhost:55432/kopano"

    environment: str = "dev"
    jwt_secret: str = DEV_JWT_SECRET
    jwt_expire_minutes: int = 30
    upload_dir: Path = Path("uploads")
    max_upload_bytes: int = 5 * 1024 * 1024
    consent_version: str = "2026-10-v1"

    # Provider selection. Only "mock" is wired; real adapters implement the same bases.
    identity_provider: str = "mock"
    registry_provider: str = "mock"
    tax_provider: str = "mock"

    llm_provider: str = "gemini"
    gemini_api_key: str = ""
    anthropic_api_key: str = ""

    cors_origins: list[str] = ["http://localhost:5173"]


settings = Settings()
