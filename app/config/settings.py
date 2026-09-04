"""
Application configuration using Pydantic Settings v2.
"""
from pathlib import Path
from typing import Literal, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Core Application
    ENVIRONMENT: Literal["development", "production", "testing"] = "development"
    APP_NAME: str = "OncoAI Chemistry & Bioactivity Data Platform"
    API_V1_STR: str = "/v1"
    DEBUG: bool = False

    # Security & Auth
    API_KEY: str = Field(default="oncoai-dev-secret-key-change-in-prod", description="Master API Key for backend SaaS integration")
    DEFAULT_TENANT_ID: str = "default-tenant"

    # Relational Database (Hot Tier)
    DATABASE_URL: str = Field(
        default="sqlite+aiosqlite:///./data/oncoai.db",
        description="Async database connection string (PostgreSQL or SQLite)"
    )

    # Object Storage (Cold Tier)
    STORAGE_BACKEND: Literal["local", "s3"] = "local"
    STORAGE_LOCAL_ROOT: Path = Path("./data/storage")
    S3_ENDPOINT_URL: Optional[str] = None
    S3_BUCKET_NAME: str = "oncoai-raw-lake"
    S3_ACCESS_KEY_ID: Optional[str] = None
    S3_SECRET_ACCESS_KEY: Optional[str] = None
    S3_REGION_NAME: str = "us-east-1"

    # Parquet Columnar Lake (Warm Tier)
    PARQUET_LAKE_PATH: Path = Path("./data/storage/parquet")

    # Scientific Processing Versions (Must remain strictly pinned and traceable)
    PIPELINE_VERSION: str = "chem-std-1.0.0"
    FINGERPRINT_VERSION: str = "morgan-r2-2048-v1"
    EXPECTED_RDKIT_VERSION: str = "2024.3.5"

    # Background Worker
    WORKER_CONCURRENCY: int = 2


# Global settings singleton
settings = Settings()
