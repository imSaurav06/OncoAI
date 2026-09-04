"""
Unified Machine-Readable API Response Envelope (Section 22 of architecture).
"""
from typing import Generic, TypeVar, Optional, Any, Dict, List
from pydantic import BaseModel, Field

T = TypeVar("T")


class ErrorDetail(BaseModel):
    code: str = Field(..., description="Stable machine-readable error code (e.g. INVALID_SMILES, NOT_FOUND)")
    message: str = Field(..., description="Human-readable description of error")
    field: Optional[str] = Field(None, description="Input field associated with error, if any")


class ResponseMeta(BaseModel):
    rdkit_version: Optional[str] = Field(None, description="Exact RDKit version used in calculation")
    pipeline_version: Optional[str] = Field(None, description="Chemistry standardization pipeline version")
    timestamp: str = Field(..., description="UTC ISO-8601 timestamp of response generation")
    duration_ms: Optional[float] = Field(None, description="Query/computation execution duration in milliseconds")
    pagination: Optional[Dict[str, Any]] = Field(None, description="Pagination metadata: total, limit, offset, has_more")


class ApiResponse(BaseModel, Generic[T]):
    schema_version: str = Field(default="1.0", description="Canonical data model schema version")
    api_version: str = Field(default="v1", description="API contract version")
    request_id: str = Field(..., description="Unique request tracing identifier")
    status: str = Field(default="success", description="'success' or 'error'")
    data: Optional[T] = Field(None, description="Payload data")
    meta: ResponseMeta = Field(..., description="Reproducibility & processing metadata")
    errors: Optional[List[ErrorDetail]] = Field(None, description="List of errors if status is 'error'")
