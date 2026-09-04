"""
Canonical Compound and Chemical Structure Models.
"""
from typing import Optional, List
from sqlalchemy import String, Float, Integer, Boolean, Text, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin


class Compound(Base, TimestampMixin):
    __tablename__ = "compounds"

    # Canonical compound identifier (e.g. CMP_01H8X...)
    compound_id: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    
    # Standard chemical representations
    canonical_smiles: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    isomeric_smiles: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    inchikey: Mapped[str] = mapped_column(String(27), unique=True, nullable=False, index=True)
    inchi: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Core physicochemical properties
    molecular_formula: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    molecular_weight: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    exact_mass: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    heavy_atom_count: Mapped[int] = mapped_column(Integer, nullable=False)
    formal_charge: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Oncology & Medicinal Chemistry Scaffold
    murcko_scaffold_smiles: Mapped[Optional[str]] = mapped_column(Text, nullable=True, index=True)
    
    # Stereochemistry indicator
    has_stereochemistry: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    # Multi-tenancy isolation (NULL = shared public reference compound, non-NULL = proprietary tenant lead)
    tenant_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)

    # Traceability & Versioning
    processing_version: Mapped[str] = mapped_column(String(64), nullable=False)
    rdkit_version: Mapped[str] = mapped_column(String(32), nullable=False)

    # Relationships
    structure: Mapped["ChemicalStructure"] = relationship(
        "ChemicalStructure", back_populates="compound", uselist=False, cascade="all, delete-orphan"
    )
    features: Mapped["MolecularFeature"] = relationship(
        "MolecularFeature", back_populates="compound", uselist=False, cascade="all, delete-orphan"
    )
    identifiers: Mapped[List["CompoundIdentifier"]] = relationship(
        "CompoundIdentifier", back_populates="compound", cascade="all, delete-orphan"
    )
    bioactivities: Mapped[List["Bioactivity"]] = relationship(
        "Bioactivity", back_populates="compound"
    )
    source_records: Mapped[List["SourceRecord"]] = relationship(
        "SourceRecord", back_populates="compound"
    )


class ChemicalStructure(Base, TimestampMixin):
    __tablename__ = "chemical_structures"

    compound_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("compounds.compound_id", ondelete="CASCADE"), primary_key=True
    )
    
    num_rings: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    num_aromatic_rings: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    num_aliphatic_rings: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    num_chiral_centers: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    num_defined_chiral_centers: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    num_undefined_chiral_centers: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    is_salt: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    salt_fragment_smiles: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    parent_compound_smiles: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    compound: Mapped["Compound"] = relationship("Compound", back_populates="structure")


class MolecularFeature(Base, TimestampMixin):
    __tablename__ = "molecular_features"

    compound_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("compounds.compound_id", ondelete="CASCADE"), primary_key=True
    )
    
    # Lipinski & Veber Descriptors
    clogp: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    tpsa: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    hbd: Mapped[int] = mapped_column(Integer, nullable=False)
    hba: Mapped[int] = mapped_column(Integer, nullable=False)
    rotatable_bonds: Mapped[int] = mapped_column(Integer, nullable=False)
    fraction_csp3: Mapped[float] = mapped_column(Float, nullable=False)

    # Precomputed Morgan Fingerprint (radius=2, 2048 bits encoded as hex string)
    morgan_fp_2048_hex: Mapped[str] = mapped_column(Text, nullable=False)
    fingerprint_version: Mapped[str] = mapped_column(String(64), nullable=False)

    compound: Mapped["Compound"] = relationship("Compound", back_populates="features")


class CompoundIdentifier(Base, TimestampMixin):
    __tablename__ = "compound_identifiers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    compound_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("compounds.compound_id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    tenant_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    
    # e.g. IUPAC_NAME, TRADE_NAME, SYNONYM, CAS_NUMBER, EXTERNAL_ACCESSION
    identifier_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    identifier_value: Mapped[str] = mapped_column(String(512), nullable=False, index=True)

    compound: Mapped["Compound"] = relationship("Compound", back_populates="identifiers")

    __table_args__ = (
        Index("ix_identifier_type_value", "identifier_type", "identifier_value"),
    )
