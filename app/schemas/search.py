"""
Compound Search and Molecular Similarity Pydantic Schemas.
"""
from typing import Optional, List
from pydantic import BaseModel, Field
from app.schemas.bioactivity import BioactivityItem


class CompoundSearchRequest(BaseModel):
    exact_inchikey: Optional[str] = Field(None, description="Exact 27-char InChIKey lookup")
    substructure_smiles: Optional[str] = Field(None, description="Substructure SMILES filter")
    min_mw: Optional[float] = Field(None, description="Minimum molecular weight (g/mol)")
    max_mw: Optional[float] = Field(None, description="Maximum molecular weight (g/mol)")
    min_clogp: Optional[float] = Field(None, description="Minimum CLogP")
    max_clogp: Optional[float] = Field(None, description="Maximum CLogP")
    min_tpsa: Optional[float] = Field(None, description="Minimum TPSA (Å²)")
    max_tpsa: Optional[float] = Field(None, description="Maximum TPSA (Å²)")
    scaffold_smiles: Optional[str] = Field(None, description="Exact Murcko scaffold match")
    molecular_formula: Optional[str] = Field(None, description="Exact molecular formula (e.g. C21H24N2O3)")
    identifier: Optional[str] = Field(None, description="Synonym, drug name, CAS, or accession ID")
    limit: int = Field(default=50, ge=1, le=500, description="Page size")
    offset: int = Field(default=0, ge=0, description="Pagination offset")


class CompoundSearchItem(BaseModel):
    compound_id: str
    canonical_smiles: str
    inchikey: str
    molecular_formula: str
    molecular_weight: float
    clogp: float
    tpsa: float
    heavy_atom_count: int
    formal_charge: int
    murcko_scaffold_smiles: Optional[str] = None


class CompoundSearchResponse(BaseModel):
    items: List[CompoundSearchItem]
    total_count: int
    limit: int
    offset: int


class SimilaritySearchRequest(BaseModel):
    smiles: str = Field(..., min_length=1, max_length=5000, description="Query chemical structure in SMILES format")
    threshold: float = Field(default=0.8, ge=0.1, le=1.0, description="Minimum Tanimoto similarity threshold (0.1 to 1.0)")
    limit: int = Field(default=50, ge=1, le=500, description="Maximum top-K similar compounds to return")
    # Optional multi-attribute bioactivity joint filters
    target_id: Optional[str] = Field(None, description="Constrain similar compounds to those active against target_id")
    activity_type: Optional[str] = Field(None, description="Activity type requirement (e.g. IC50, Ki)")
    max_activity_nm: Optional[float] = Field(None, description="Potency threshold in nM (e.g. <= 500 nM)")


class SimilarityResultItem(BaseModel):
    compound_id: str
    canonical_smiles: str
    inchikey: str
    similarity_score: float = Field(..., ge=0.0, le=1.0, description="Tanimoto similarity coefficient")
    molecular_formula: str
    molecular_weight: float
    clogp: float
    tpsa: float
    murcko_scaffold_smiles: Optional[str] = None
    bioactivities: Optional[List[BioactivityItem]] = None


class SimilaritySearchResponse(BaseModel):
    query_smiles: str
    query_canonical_smiles: str
    query_inchikey: str
    threshold: float
    limit: int
    total_matches: int
    items: List[SimilarityResultItem]
