"""
Provenance, ProcessingRun, and RejectedRecord Models for Scientific Traceability and QC.
"""
from typing import Optional, List
from datetime import datetime
from sqlalchemy import String, Integer, Text, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin, utc_now


class ProcessingRun(Base, TimestampMixin):
    __tablename__ = "processing_runs"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dataset_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("datasets.dataset_id", ondelete="SET NULL"), nullable=True, index=True
    )
    
    pipeline_version: Mapped[str] = mapped_column(String(64), nullable=False)
    rdkit_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="RUNNING", nullable=False)  # RUNNING, COMPLETED, FAILED
    
    # Audit statistics
    total_records: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    valid_records: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rejected_records: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicate_records: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    provenance_records: Mapped[List["Provenance"]] = relationship("Provenance", back_populates="processing_run")


class Provenance(Base, TimestampMixin):
    __tablename__ = "provenance"

    provenance_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_record_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("source_records.source_record_id", ondelete="SET NULL"), nullable=True, index=True
    )
    processing_run_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("processing_runs.run_id", ondelete="SET NULL"), nullable=True, index=True
    )
    
    pipeline_version: Mapped[str] = mapped_column(String(64), nullable=False)
    rdkit_version: Mapped[str] = mapped_column(String(32), nullable=False)
    normalization_version: Mapped[str] = mapped_column(String(64), default="norm-v1.0", nullable=False)

    processing_run: Mapped[Optional["ProcessingRun"]] = relationship("ProcessingRun", back_populates="provenance_records")


class RejectedRecord(Base, TimestampMixin):
    __tablename__ = "rejected_records"

    rejection_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_record_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("source_records.source_record_id", ondelete="CASCADE"), nullable=True, index=True
    )
    
    # PARSE_ERROR, VALENCE_ERROR, SANITIZE_ERROR, STANDARDIZE_ERROR, UNIT_UNKNOWN
    rejection_category: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    raw_data_snippet: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    pipeline_version: Mapped[str] = mapped_column(String(64), nullable=False)
    rdkit_version: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (
        Index("ix_rejection_cat_date", "rejection_category", "created_at"),
    )
