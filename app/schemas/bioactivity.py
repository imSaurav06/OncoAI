"""
Bioactivity Search Request and Response Pydantic Schemas.
"""
from typing import Optional, List
from pydantic import BaseModel, Field


class BioactivitySearchRequest(BaseModel):
    compound_id: Optional[str] = Field(None, description="Exact internal compound ID filter")
    target_id: Optional[str] = Field(None, description="Target identifier (e.g. TGT_EGFR)")
    gene_symbol: Optional[str] = Field(None, description="Target gene symbol (e.g. EGFR, BRAF, KRAS)")
    cell_line: Optional[str] = Field(None, description="Oncology cell line (e.g. MCF-7, A549, K562)")
    activity_type: Optional[str] = Field(None, description="Activity type (IC50, Ki, EC50, GI50, % INHIBITION)")
    min_normalized_value: Optional[float] = Field(None, description="Minimum normalized activity value (in nM)")
    max_normalized_value: Optional[float] = Field(None, description="Maximum normalized activity value (in nM)")
    min_p_activity: Optional[float] = Field(None, description="Minimum -log10 Molar potency (e.g. 7.0 for 100 nM)")
    is_experimental: Optional[bool] = Field(None, description="Filter for in-house wet-lab feedback vs public data")
    source_id: Optional[str] = Field(None, description="Filter by data source (e.g. SRC_CHEMBL, SRC_PUBCHEM)")
    limit: int = Field(default=50, ge=1, le=1000, description="Page size (max 1000)")
    offset: int = Field(default=0, ge=0, description="Pagination offset")


class BioactivityItem(BaseModel):
    bioactivity_id: str
    compound_id: str
    canonical_smiles: Optional[str] = None
    target_id: Optional[str] = None
    target_name: Optional[str] = None
    gene_symbol: Optional[str] = None
    cell_line: Optional[str] = None
    assay_type: Optional[str] = None
    activity_type: str
    
    # Original scientific observation
    original_relation: Optional[str] = "="
    original_value: float
    original_unit: str
    
    # Normalized canonical value (nM or %)
    normalized_relation: Optional[str] = "="
    normalized_value: float
    normalized_unit: str
    p_activity: Optional[float] = None
    
    is_experimental: bool = False
    source_name: Optional[str] = None
    external_id: Optional[str] = None
    provenance_id: Optional[str] = None


class BioactivitySearchResponse(BaseModel):
    items: List[BioactivityItem]
    total_count: int
    limit: int
    offset: int
