"""
Compound and Chemical Analysis Pydantic Schemas.
"""
from typing import Optional, List, Dict
from pydantic import BaseModel, Field


class StandardizeRequest(BaseModel):
    smiles: str = Field(..., min_length=1, max_length=5000, description="Raw chemical structure in SMILES format")


class StandardizeResponse(BaseModel):
    canonical_smiles: str = Field(..., description="Deterministically standardized canonical SMILES")
    inchikey: str = Field(..., description="Standard 27-character InChIKey")
    inchi: Optional[str] = Field(None, description="Standard InChI string")
    status: str = Field(default="valid", description="Validation status ('valid', 'modified', 'rejected')")
    was_modified: bool = Field(..., description="Indicates if standardization altered original connectivity/charges")
    salt_removed: bool = Field(..., description="Indicates if salt or counter-ion was stripped")
    charge_neutralized: bool = Field(..., description="Indicates if charges were uncharged/neutralized")
    salt_fragment_smiles: Optional[str] = Field(None, description="SMILES of stripped salt counter-ion if present")


class MolecularDescriptors(BaseModel):
    molecular_weight: float = Field(..., description="Molecular weight (g/mol)")
    exact_mass: Optional[float] = Field(None, description="Exact monoisotopic mass")
    molecular_formula: str = Field(..., description="Hill system chemical formula")
    heavy_atom_count: int = Field(..., description="Total count of non-hydrogen atoms")
    formal_charge: int = Field(..., description="Net formal molecular charge")
    clogp: float = Field(..., description="Calculated octanol-water partition coefficient (Wildman-Crippen)")
    tpsa: float = Field(..., description="Topological polar surface area (Å²)")
    hbd: int = Field(..., description="Lipinski hydrogen bond donors (OH + NH)")
    hba: int = Field(..., description="Lipinski hydrogen bond acceptors (N + O)")
    rotatable_bonds: int = Field(..., description="Count of rotatable non-terminal single bonds")
    fraction_csp3: float = Field(..., description="Fraction of SP3 hybridized carbons (Fsp3)")
    num_rings: int = Field(..., description="Total ring count")
    num_aromatic_rings: int = Field(..., description="Count of aromatic rings")
    num_aliphatic_rings: int = Field(..., description="Count of aliphatic rings")
    num_chiral_centers: int = Field(..., description="Total chiral centers")


class AnalyzeRequest(BaseModel):
    smiles: str = Field(..., min_length=1, max_length=5000, description="Chemical structure in SMILES format")


class AnalyzeResponse(BaseModel):
    canonical_smiles: str
    isomeric_smiles: Optional[str]
    inchikey: str
    inchi: Optional[str]
    murcko_scaffold_smiles: Optional[str] = Field(None, description="Bemis-Murcko core carbon skeleton")
    descriptors: MolecularDescriptors
    fingerprint_summary: Dict[str, int] = Field(..., description="Fingerprint metadata: n_bits, on_bits_count")
    fingerprint_hex: str = Field(..., description="Morgan (radius 2, 2048-bit) fingerprint hex encoded")
    was_standardized: bool


class CompoundIdentifierItem(BaseModel):
    identifier_type: str
    identifier_value: str
    source_id: Optional[str] = None


class CompoundDetailResponse(BaseModel):
    compound_id: str
    canonical_smiles: str
    isomeric_smiles: Optional[str]
    inchikey: str
    inchi: Optional[str]
    molecular_formula: str
    molecular_weight: float
    exact_mass: Optional[float]
    heavy_atom_count: int
    formal_charge: int
    murcko_scaffold_smiles: Optional[str]
    processing_version: str
    rdkit_version: str
    created_at: str
    
    # Nested components
    descriptors: Optional[MolecularDescriptors] = None
    identifiers: List[CompoundIdentifierItem] = Field(default_factory=list)
    bioactivity_count: int = 0
    source_count: int = 0
