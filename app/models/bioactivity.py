"""
Bioactivity, Assay, Target, CellLine, and Organism Models.
"""
from typing import Optional, List
from sqlalchemy import String, Float, Integer, Boolean, Text, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin


class Organism(Base, TimestampMixin):
    __tablename__ = "organisms"

    organism_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scientific_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    common_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    ncbi_taxonomy_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    targets: Mapped[List["Target"]] = relationship("Target", back_populates="organism")


class Target(Base, TimestampMixin):
    __tablename__ = "targets"

    target_id: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    target_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)  # PROTEIN, COMPLEX, CELL
    uniprot_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    gene_symbol: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    
    organism_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("organisms.organism_id", ondelete="SET NULL"), nullable=True
    )

    organism: Mapped[Optional["Organism"]] = relationship("Organism", back_populates="targets")
    assays: Mapped[List["Assay"]] = relationship("Assay", back_populates="target")


class CellLine(Base, TimestampMixin):
    __tablename__ = "cell_lines"

    cell_line_id: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    tissue_origin: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    cancer_type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    disease: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    assays: Mapped[List["Assay"]] = relationship("Assay", back_populates="cell_line")


class Assay(Base, TimestampMixin):
    __tablename__ = "assays"

    assay_id: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    assay_name: Mapped[str] = mapped_column(String(256), nullable=False)
    assay_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)  # BINDING, CELL_GROWTH, FUNCTIONAL, ADMET
    
    target_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("targets.target_id", ondelete="SET NULL"), nullable=True, index=True
    )
    cell_line_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("cell_lines.cell_line_id", ondelete="SET NULL"), nullable=True, index=True
    )
    organism_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("organisms.organism_id", ondelete="SET NULL"), nullable=True
    )
    
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    curation_status: Mapped[str] = mapped_column(String(32), default="CURATED", nullable=False)
    
    # Multi-tenancy isolation (NULL = public assay, non-NULL = proprietary tenant assay)
    tenant_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)

    target: Mapped[Optional["Target"]] = relationship("Target", back_populates="assays")
    cell_line: Mapped[Optional["CellLine"]] = relationship("CellLine", back_populates="assays")
    bioactivities: Mapped[List["Bioactivity"]] = relationship("Bioactivity", back_populates="assay")


class Bioactivity(Base, TimestampMixin):
    __tablename__ = "bioactivities"

    bioactivity_id: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    
    compound_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("compounds.compound_id", ondelete="CASCADE"), nullable=False, index=True
    )
    assay_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("assays.assay_id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_record_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("source_records.source_record_id", ondelete="SET NULL"), nullable=True, index=True
    )
    provenance_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("provenance.provenance_id", ondelete="SET NULL"), nullable=True
    )

    # Distinguish public literature/database data from proprietary wet-lab / experimental feedback
    is_experimental: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    # Multi-tenancy isolation (NULL = shared public bioactivity, non-NULL = private tenant measurement)
    tenant_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)

    # Activity measurement (Heterogeneous types: IC50, EC50, Ki, Kd, GI50, % Inhibition, etc.)
    activity_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Original Scientific Values (Unaltered)
    original_relation: Mapped[Optional[str]] = mapped_column(String(16), default="=", nullable=True)
    original_value: Mapped[float] = mapped_column(Float, nullable=False)
    original_unit: Mapped[str] = mapped_column(String(64), nullable=False)

    # Normalized Scientific Values (Canonical: nM for concentration, % for inhibition)
    normalized_relation: Mapped[Optional[str]] = mapped_column(String(16), default="=", nullable=True)
    normalized_value: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    normalized_unit: Mapped[str] = mapped_column(String(64), nullable=False)

    # pActivity (-log10 Molar, e.g. pIC50, pKi for ML-ready modeling)
    # Notice p_activity_relation inverts on negative logarithm (e.g. > 10,000 nM -> pIC50 < 5.0)
    p_activity: Mapped[Optional[float]] = mapped_column(Float, nullable=True, index=True)
    p_activity_relation: Mapped[Optional[str]] = mapped_column(String(16), default="=", nullable=True)
    is_censored: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    is_approximate: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    # Relationships
    compound: Mapped["Compound"] = relationship("Compound", back_populates="bioactivities")
    assay: Mapped["Assay"] = relationship("Assay", back_populates="bioactivities")
    source_record: Mapped[Optional["SourceRecord"]] = relationship("SourceRecord")
    provenance: Mapped[Optional["Provenance"]] = relationship("Provenance")

    __table_args__ = (
        Index("ix_bioact_comp_type_norm", "compound_id", "activity_type", "normalized_value"),
        Index("ix_bioact_assay_type_norm", "assay_id", "activity_type", "normalized_value"),
    )
