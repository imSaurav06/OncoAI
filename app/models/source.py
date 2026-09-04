"""
Source, Dataset, and SourceRecord Models.
"""
from typing import Optional, List
from sqlalchemy import String, Integer, Boolean, Text, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin


class Source(Base, TimestampMixin):
    __tablename__ = "sources"

    source_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)  # PUBLIC_DATABASE, LITERATURE, EXPERIMENTAL
    homepage_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    
    # Governance & Licensing (Section 42 of architecture)
    license_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    license_terms: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_commercial_allowed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    acquisition_method: Mapped[str] = mapped_column(String(64), default="API_SYNC", nullable=False)

    datasets: Mapped[List["Dataset"]] = relationship("Dataset", back_populates="source")
    source_records: Mapped[List["SourceRecord"]] = relationship("SourceRecord", back_populates="source")


class Dataset(Base, TimestampMixin):
    __tablename__ = "datasets"

    dataset_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sources.source_id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    record_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Multi-tenancy isolation (NULL = shared public dataset, non-NULL = proprietary tenant dataset)
    tenant_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)

    source: Mapped["Source"] = relationship("Source", back_populates="datasets")
    source_records: Mapped[List["SourceRecord"]] = relationship("SourceRecord", back_populates="dataset")


class SourceRecord(Base, TimestampMixin):
    __tablename__ = "source_records"

    source_record_id: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    source_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sources.source_id", ondelete="CASCADE"), nullable=False, index=True
    )
    dataset_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("datasets.dataset_id", ondelete="SET NULL"), nullable=True, index=True
    )
    
    # Identifier in upstream database (e.g. CHEMBL25, CID_2244)
    external_id: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    
    # Reference to immutable raw payload in Layer A (S3 / Object Store)
    raw_payload_uri: Mapped[str] = mapped_column(String(512), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)  # SHA-256
    
    # Raw structure as received from source (unaltered SMILES or MOL block)
    raw_structure_string: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Entity resolution link (Resolved Canonical Compound)
    compound_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("compounds.compound_id", ondelete="SET NULL"), nullable=True, index=True
    )
    
    # INGESTED, PROCESSED, REJECTED
    status: Mapped[str] = mapped_column(String(32), default="INGESTED", nullable=False, index=True)

    # Multi-tenancy isolation
    tenant_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)

    source: Mapped["Source"] = relationship("Source", back_populates="source_records")
    dataset: Mapped[Optional["Dataset"]] = relationship("Dataset", back_populates="source_records")
    compound: Mapped[Optional["Compound"]] = relationship("Compound", back_populates="source_records")

    __table_args__ = (
        Index("ix_source_external_id", "source_id", "external_id"),
        UniqueConstraint("dataset_id", "external_id", name="uq_source_records_dataset_external"),
    )
