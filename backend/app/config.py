from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


DEV_JWT_SECRET = "dev-only-secret-not-for-production-use-0000"
MIN_JWT_SECRET_BYTES = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)

    # The app connects as kopano_app (no UPDATE/DELETE on audit). seed.py uses the admin URL.
    database_url: str = "postgresql+psycopg2://kopano_app:kopano_app_dev@localhost:55432/kopano"
    admin_database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:55432/kopano"

    environment: str = "dev"
    mfa_encryption_key: str = ""  # a Fernet key; required outside dev
    jwt_secret: str = DEV_JWT_SECRET
    jwt_expire_minutes: int = 30
    upload_dir: Path = Path("uploads")
    max_upload_bytes: int = 5 * 1024 * 1024
    consent_version: str = "2026-10-v1"

    # Provider selection. Only "mock" is wired; real adapters implement the same bases.
    identity_provider: str = "mock"
    registry_provider: str = "mock"
    tax_provider: str = "mock"
    scanner_provider: str = "mock"  # "clamav" for real scanning; required outside dev
    clamav_host: str = "127.0.0.1"
    clamav_port: int = 33100  # our compose maps clamd to this host port
    clamav_timeout: float = 20.0

    # Email: "log" keeps messages in memory; "brevo" sends them (needs a verified sender)
    email_provider: str = "log"
    brevo_api_key: str = ""
    email_from: str = ""
    email_from_name: str = "Kopano Match"
    app_url: str = "http://localhost:5173"

    llm_provider: str = "gemini"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"  # change in .env if Google retires it
    anthropic_api_key: str = ""

    cors_origins: list[str] = ["http://localhost:5173"]


settings = Settings()
