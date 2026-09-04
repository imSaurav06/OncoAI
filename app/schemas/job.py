"""
Job, Source, and Dataset Pydantic Schemas.
"""
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class CreateJobRequest(BaseModel):
    job_type: str = Field(..., description="Type of job: INGESTION, BULK_STANDARDIZE, BULK_SIMILARITY, INDEX_BUILD")
    input_params: Dict[str, Any] = Field(default_factory=dict, description="Job configuration and input parameters")


class JobStatusResponse(BaseModel):
    job_id: str
    job_type: str
    status: str = Field(..., description="QUEUED, RUNNING, COMPLETED, FAILED, CANCELLED")
    progress_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    input_params: Optional[Dict[str, Any]] = None
    result_summary: Optional[Dict[str, Any]] = None
    error_details: Optional[Dict[str, Any]] = None
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class DatasetResponse(BaseModel):
    dataset_id: str
    source_id: str
    name: str
    version: str
    description: Optional[str] = None
    record_count: int
    created_at: str


class SourceResponse(BaseModel):
    source_id: str
    name: str
    source_type: str
    homepage_url: Optional[str] = None
    license_name: Optional[str] = None
    license_terms: Optional[str] = None
    is_commercial_allowed: bool
    acquisition_method: str
    datasets: List[DatasetResponse] = Field(default_factory=list)
