"""Centralized, validated configuration for DecisionRoom.

Provides strict settings validation, approved model registries,
safe secret redaction (no secrets in repr/str/logs), and path resolutions.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Set
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator

# Root project directory
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Load .env file from project root if it exists (override system env so configured keys take precedence)
load_dotenv(PROJECT_ROOT / ".env", override=True)


# Approved Model Registry as specified in IMPLEMENTATION_PLAN.md Section 3.2
APPROVED_MODEL_IDS: Set[str] = {
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-3.7-flash",
    "gemma-4-26b-a4b-it",
    "gemma-4-31b-it",
    "nvidia/nemotron-3-super-120b-a12b",
    # Legacy compatibility fallback
    "openai/gpt-oss-20b",
}

NVIDIA_NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"
FIRECRAWL_BASE_URL_DEFAULT = "https://api.firecrawl.dev"


def redact_secret(val: str | None) -> str:
    """Return a redacted representation of a secret string."""
    if not val:
        return "[NOT CONFIGURED]"
    clean = val.strip()
    if len(clean) <= 8:
        return "[REDACTED]"
    return f"{clean[:4]}...{clean[-4:]}"


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default


class Settings(BaseModel):
    """Immutable, validated system configuration."""

    # Project directories
    project_root: Path = Field(default=PROJECT_ROOT)
    reports_dir: Path = Field(default=PROJECT_ROOT / "reports")
    storage_dir: Path = Field(default=PROJECT_ROOT / "storage")
    sqlite_path: Path = Field(default=PROJECT_ROOT / "storage" / "decisionroom.db")
    qdrant_local_path: Path = Field(default=PROJECT_ROOT / "storage" / "qdrant")

    # API Keys & Endpoints
    nvidia_nim_api_key: str = Field(default_factory=lambda: os.getenv("NVIDIA_NIM_API_KEY", "").strip())
    nvidia_nim_base_url: str = Field(default_factory=lambda: os.getenv("NVIDIA_NIM_BASE_URL", NVIDIA_NIM_BASE_URL).strip())
    google_api_key: str = Field(default_factory=lambda: os.getenv("GOOGLE_API_KEY", "").strip())
    qdrant_url: str = Field(default_factory=lambda: os.getenv("QDRANT_URL", "").strip())
    qdrant_api_key: str = Field(default_factory=lambda: os.getenv("QDRANT_API_KEY", "").strip())
    firecrawl_api_key: str = Field(default_factory=lambda: os.getenv("FIRECRAWL_API_KEY", "").strip())
    firecrawl_base_url: str = Field(default_factory=lambda: os.getenv("FIRECRAWL_BASE_URL", FIRECRAWL_BASE_URL_DEFAULT).strip())

    # Provider & Model routing
    default_llm_provider: str = Field(default_factory=lambda: os.getenv("DEFAULT_LLM_PROVIDER", "nvidia").lower().strip())
    model_intake: str = Field(default_factory=lambda: os.getenv("MODEL_INTAKE", "gemini-3.1-flash-lite").strip())
    model_fallback: str = Field(default_factory=lambda: os.getenv("MODEL_FALLBACK", "gemini-3.5-flash-lite").strip())
    model_specialist: str = Field(default_factory=lambda: os.getenv("MODEL_SPECIALIST", "gemma-4-26b-a4b-it").strip())
    model_specialist_review: str = Field(default_factory=lambda: os.getenv("MODEL_SPECIALIST_REVIEW", "gemma-4-31b-it").strip())
    model_decision: str = Field(default_factory=lambda: os.getenv("MODEL_DECISION", "nvidia/nemotron-3-super-120b-a12b").strip())
    model_planner: str = Field(default_factory=lambda: os.getenv("MODEL_PLANNER", "nvidia/nemotron-3-super-120b-a12b").strip())
    model_critic: str = Field(default_factory=lambda: os.getenv("MODEL_CRITIC", "nvidia/nemotron-3-super-120b-a12b").strip())

    # Concurrency and Rate Limits — all read from env vars; defaults are user-reported starting limits
    max_agent_concurrency: int = Field(default_factory=lambda: _env_int("MAX_AGENT_CONCURRENCY", 2))
    max_retries: int = Field(default_factory=lambda: _env_int("MAX_RETRIES", 2))
    request_timeout_seconds: int = Field(default_factory=lambda: _env_int("REQUEST_TIMEOUT_SECONDS", 60))
    # Per-provider RPM caps. Defaults: Gemma 4 26B/31B=30, Gemini flash-lite=15, NVIDIA NIM=40
    rate_limit_gemma_rpm: int = Field(default_factory=lambda: _env_int("RATE_LIMIT_GEMMA_RPM", 30))
    rate_limit_gemini_rpm: int = Field(default_factory=lambda: _env_int("RATE_LIMIT_GEMINI_RPM", 15))
    rate_limit_nvidia_rpm: int = Field(default_factory=lambda: _env_int("RATE_LIMIT_NVIDIA_RPM", 40))

    # Embedding configuration
    embedding_provider: str = Field(default_factory=lambda: os.getenv("EMBEDDING_PROVIDER", "huggingface").strip())
    embedding_model_name: str = Field(default_factory=lambda: os.getenv("EMBEDDING_MODEL_NAME", "nomic-ai/nomic-embed-text-v1.5").strip())
    embedding_dimension: int = Field(default_factory=lambda: _env_int("EMBEDDING_DIMENSION", 768))

    @field_validator(
        "model_intake", "model_fallback", "model_specialist", "model_specialist_review",
        "model_decision", "model_planner", "model_critic",
    )
    @classmethod
    def validate_model_id(cls, value: str) -> str:
        if value not in APPROVED_MODEL_IDS:
            raise ValueError(
                f"Model '{value}' is not in the approved model registry: {sorted(APPROVED_MODEL_IDS)}"
            )
        return value

    @property
    def is_nvidia_configured(self) -> bool:
        return bool(self.nvidia_nim_api_key)

    @property
    def is_google_configured(self) -> bool:
        return bool(self.google_api_key)

    @property
    def is_qdrant_configured(self) -> bool:
        return bool(self.qdrant_url and self.qdrant_api_key)

    @property
    def is_firecrawl_configured(self) -> bool:
        return bool(self.firecrawl_api_key)

    def ensure_directories(self) -> None:
        """Create necessary directories if they do not exist."""
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.qdrant_local_path.mkdir(parents=True, exist_ok=True)

    def safe_dict(self) -> Dict[str, Any]:
        """Export dictionary with all sensitive API keys safely redacted."""
        return {
            "default_llm_provider": self.default_llm_provider,
            "is_nvidia_configured": self.is_nvidia_configured,
            "is_google_configured": self.is_google_configured,
            "is_qdrant_configured": self.is_qdrant_configured,
            "is_firecrawl_configured": self.is_firecrawl_configured,
            "nvidia_nim_api_key": redact_secret(self.nvidia_nim_api_key),
            "nvidia_nim_base_url": self.nvidia_nim_base_url,
            "google_api_key": redact_secret(self.google_api_key),
            "firecrawl_api_key": redact_secret(self.firecrawl_api_key),
            "qdrant_url": self.qdrant_url if self.qdrant_url else "[NOT CONFIGURED]",
            "qdrant_api_key": redact_secret(self.qdrant_api_key),
            "model_intake": self.model_intake,
            "model_specialist": self.model_specialist,
            "model_specialist_review": self.model_specialist_review,
            "model_decision": self.model_decision,
            "model_planner": self.model_planner,
            "model_critic": self.model_critic,
            "embedding_provider": self.embedding_provider,
            "embedding_model_name": self.embedding_model_name,
            "embedding_dimension": self.embedding_dimension,
            "approved_models": sorted(APPROVED_MODEL_IDS),
            "max_agent_concurrency": self.max_agent_concurrency,
            "max_retries": self.max_retries,
            "request_timeout_seconds": self.request_timeout_seconds,
            "rate_limit_gemma_rpm": self.rate_limit_gemma_rpm,
            "rate_limit_gemini_rpm": self.rate_limit_gemini_rpm,
            "rate_limit_nvidia_rpm": self.rate_limit_nvidia_rpm,
            "sqlite_path": str(self.sqlite_path),
            "qdrant_local_path": str(self.qdrant_local_path),
        }

    def __repr__(self) -> str:
        items = [f"{k}={v!r}" for k, v in self.safe_dict().items()]
        return f"Settings({', '.join(items)})"

    def __str__(self) -> str:
        return self.__repr__()


# Singleton configuration instance
settings = Settings()
settings.ensure_directories()
