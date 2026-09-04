"""
Asynchronous Job Management API Endpoints (Section 19 of architecture).
"""
import time
import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
import rdkit

from app.config.settings import settings
from app.storage.database import get_db
from app.security.auth import verify_api_key, TenantContext
from app.api.dependencies import get_request_id
from app.api.middleware import create_error_response
from app.schemas.envelope import ApiResponse, ResponseMeta
from app.schemas.job import CreateJobRequest, JobStatusResponse
from app.jobs.worker import job_manager
from app.jobs.tasks import run_ingestion_task
from app.ingestion.chembl_adapter import ChEMBLAdapter
from app.ingestion.pubchem_adapter import PubChemAdapter
from app.ingestion.inhouse_adapter import InHouseExperimentAdapter

router = APIRouter(prefix="/jobs", tags=["Asynchronous Jobs"])


@router.post(
    "",
    response_model=ApiResponse[JobStatusResponse],
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit asynchronous processing job",
    description="Submits a background task for large ingestion, bulk standardization, or index generation.",
)
async def submit_job(
    payload: CreateJobRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth: TenantContext = Depends(verify_api_key),
):
    req_id = get_request_id(request)
    start_time = time.perf_counter()

    job = await job_manager.create_job(
        db=db,
        job_type=payload.job_type,
        input_params=payload.input_params,
        tenant_id=auth.tenant_id,
    )

    # Dispatch ingestion task if INGESTION
    if payload.job_type == "INGESTION":
        src_id = payload.input_params.get("source_id", "SRC_CHEMBL")
        adapter_map = {
            "SRC_CHEMBL": ChEMBLAdapter(),
            "SRC_PUBCHEM": PubChemAdapter(),
            "SRC_INHOUSE_LAB": InHouseExperimentAdapter(),
        }
        adapter = adapter_map.get(src_id, ChEMBLAdapter())
        ds_name = payload.input_params.get("dataset_name", f"Ingestion {src_id}")
        ds_ver = payload.input_params.get("dataset_version", "v1.0")
        raw_records = payload.input_params.get("records", [])

        job_manager.dispatch_job(
            job.job_id,
            run_ingestion_task,
            source_adapter=adapter,
            dataset_name=ds_name,
            dataset_version=ds_ver,
            raw_records_data=raw_records,
            tenant_id=auth.tenant_id,
        )

    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
    meta = ResponseMeta(
        rdkit_version=rdkit.__version__,
        pipeline_version=settings.PIPELINE_VERSION,
        timestamp=datetime.now(timezone.utc).isoformat(),
        duration_ms=duration_ms,
    )

    data = JobStatusResponse(
        job_id=job.job_id,
        job_type=job.job_type,
        status=job.status,
        progress_pct=job.progress_pct,
        input_params=payload.input_params,
        result_summary=None,
        error_details=None,
        created_at=job.created_at.isoformat(),
    )

    return ApiResponse(request_id=req_id, status="success", data=data, meta=meta)


@router.get(
    "/{job_id}",
    response_model=ApiResponse[JobStatusResponse],
    summary="Get job execution status and results",
)
async def get_job_status(
    job_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth: TenantContext = Depends(verify_api_key),
):
    req_id = get_request_id(request)
    start_time = time.perf_counter()

    job = await job_manager.get_job(db, job_id)
    if not job or (not auth.is_admin and job.tenant_id is not None and job.tenant_id != auth.tenant_id):
        return create_error_response(
            req_id, status.HTTP_404_NOT_FOUND, "JOB_NOT_FOUND", f"Job {job_id} not found"
        )

    input_params = json.loads(job.input_params_json) if job.input_params_json else None
    result_summary = json.loads(job.result_summary_json) if job.result_summary_json else None
    error_details = json.loads(job.error_details_json) if job.error_details_json else None

    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
    meta = ResponseMeta(
        rdkit_version=rdkit.__version__,
        pipeline_version=settings.PIPELINE_VERSION,
        timestamp=datetime.now(timezone.utc).isoformat(),
        duration_ms=duration_ms,
    )

    data = JobStatusResponse(
        job_id=job.job_id,
        job_type=job.job_type,
        status=job.status,
        progress_pct=job.progress_pct,
        input_params=input_params,
        result_summary=result_summary,
        error_details=error_details,
        created_at=job.created_at.isoformat(),
        started_at=job.started_at.isoformat() if job.started_at else None,
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
    )

    return ApiResponse(request_id=req_id, status="success", data=data, meta=meta)
