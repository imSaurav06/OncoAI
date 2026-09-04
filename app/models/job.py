"""
Asynchronous Job Execution Model.
"""
from typing import Optional
from datetime import datetime
from sqlalchemy import String, Integer, Text, DateTime, Float
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin


class Job(Base, TimestampMixin):
    __tablename__ = "jobs"

    job_id: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    # INGESTION, BULK_STANDARDIZE, BULK_SIMILARITY, INDEX_BUILD, REPROCESSING
    job_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    
    # Multi-tenancy isolation (NULL = system/admin job, non-NULL = tenant specific job)
    tenant_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    
    # QUEUED, RUNNING, COMPLETED, FAILED, CANCELLED
    status: Mapped[str] = mapped_column(String(32), default="QUEUED", nullable=False, index=True)
    progress_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    
    # Serialized parameters and outcomes
    input_params_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    result_summary_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_details_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
