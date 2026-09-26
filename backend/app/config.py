"""Centralized application configuration.

All environment access goes through `Settings`. Never read os.environ elsewhere.
Model IDs, voice IDs and feature flags live here so they can be swapped without code changes.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import Field, SecretStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"

    # --- Database -----------------------------------------------------------
    database_url: str = "postgresql+asyncpg://ambient:ambient@localhost:5433/ambient"
    db_echo: bool = False

    # --- Gemini -------------------------------------------------------------
    google_api_key: SecretStr | None = None
    gemini_model: str = "gemini-3.8-flash"
    gemini_embedding_model: str = "gemini-embedding-2"
    # Single source of truth for the pgvector column dimension.
    gemini_embedding_dimension: int = 768
    gemini_timeout_s: float = 20.0

    # --- ElevenLabs ---------------------------------------------------------
    elevenlabs_api_key: SecretStr | None = None
    elevenlabs_voice_id: str = ""
    elevenlabs_tts_model: str = "eleven_flash_v2_5"
    elevenlabs_stt_model: str = "scribe_v1"
    elevenlabs_base_url: str = "https://api.elevenlabs.io"
    elevenlabs_timeout_s: float = 30.0

    # --- Mock-first flags ---------------------------------------------------
    use_mock_ai: bool = True
    use_mock_voice: bool = True
    mock_stt_text: str = "What's changed with Novara since I last looked at it?"

    # --- URLs / paths -------------------------------------------------------
    frontend_url: str = "http://localhost:3000"
    backend_url: str = "http://localhost:8000"
    data_dir: Path = Field(default=REPO_ROOT / "data")

    # --- Personalization (hackathon heuristic) ------------------------------
    # Interest scores halve after this many days without interaction; 0 disables decay.
    interest_half_life_days: float = 90.0

    # --- Retrieval ----------------------------------------------------------
    retrieval_default_limit: int = 8
    retrieval_candidate_pool: int = 40

    @computed_field  # type: ignore[prop-decorator]
    @property
    def ai_is_mocked(self) -> bool:
        """Mock AI when explicitly requested OR when no key is configured."""
        return self.use_mock_ai or not _has_secret(self.google_api_key)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def voice_is_mocked(self) -> bool:
        return self.use_mock_voice or not _has_secret(self.elevenlabs_api_key)

    @property
    def async_database_url(self) -> str:
        """DATABASE_URL normalized for SQLAlchemy + asyncpg.

        Accepts `postgres://` / `postgresql://` URLs (as copied from Tiger Data) and drops
        libpq-only query params (sslmode) that asyncpg does not understand; SSL is passed via
        `database_connect_args` instead.
        """
        parts = urlsplit(self.database_url)
        scheme = parts.scheme
        if scheme in {"postgres", "postgresql", "postgresql+psycopg", "postgresql+psycopg2"}:
            scheme = "postgresql+asyncpg"
        query = [(k, v) for k, v in parse_qsl(parts.query) if k not in {"sslmode", "channel_binding"}]
        return urlunsplit((scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))

    @property
    def database_connect_args(self) -> dict[str, object]:
        query = dict(parse_qsl(urlsplit(self.database_url).query))
        if query.get("sslmode") in {"require", "verify-ca", "verify-full"}:
            return {"ssl": "require"}
        return {}

    @property
    def cors_origins(self) -> list[str]:
        return [self.frontend_url, "http://localhost:3000", "http://127.0.0.1:3000"]


def _has_secret(value: SecretStr | None) -> bool:
    return value is not None and bool(value.get_secret_value().strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
