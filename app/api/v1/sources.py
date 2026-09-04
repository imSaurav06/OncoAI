"""
Sources & Datasets Metadata Endpoints (Section 18 of architecture).
"""
import time
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
import rdkit

from app.config.settings import settings
from app.storage.database import get_db
from app.security.auth import verify_api_key
from app.api.dependencies import get_request_id
from app.api.middleware import create_error_response
from app.schemas.envelope import ApiResponse, ResponseMeta
from app.schemas.job import SourceResponse, DatasetResponse
from app.models.source import Source, Dataset

router = APIRouter(tags=["Sources & Datasets"])


@router.get(
    "/sources/{source_id}",
    response_model=ApiResponse[SourceResponse],
    summary="Get source details and licensing metadata",
)
async def get_source(
    source_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    req_id = get_request_id(request)
    start_time = time.perf_counter()

    stmt = select(Source).where(Source.source_id == source_id).options(selectinload(Source.datasets))
    res = await db.execute(stmt)
    source = res.scalar_one_or_none()

    if not source:
        return create_error_response(
            req_id, status.HTTP_404_NOT_FOUND, "SOURCE_NOT_FOUND", f"Source {source_id} not found"
        )

    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
    meta = ResponseMeta(
        rdkit_version=rdkit.__version__,
        pipeline_version=settings.PIPELINE_VERSION,
        timestamp=datetime.now(timezone.utc).isoformat(),
        duration_ms=duration_ms,
    )

    data = SourceResponse(
        source_id=source.source_id,
        name=source.name,
        source_type=source.source_type,
        homepage_url=source.homepage_url,
        license_name=source.license_name,
        license_terms=source.license_terms,
        is_commercial_allowed=source.is_commercial_allowed,
        acquisition_method=source.acquisition_method,
        datasets=[
            DatasetResponse(
                dataset_id=ds.dataset_id,
                source_id=ds.source_id,
                name=ds.name,
                version=ds.version,
                description=ds.description,
                record_count=ds.record_count,
                created_at=ds.created_at.isoformat(),
            )
            for ds in source.datasets
        ],
    )

    return ApiResponse(request_id=req_id, status="success", data=data, meta=meta)


@router.get(
    "/datasets/{dataset_id}",
    response_model=ApiResponse[DatasetResponse],
    summary="Get dataset details and record counts",
)
async def get_dataset(
    dataset_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    req_id = get_request_id(request)
    start_time = time.perf_counter()

    stmt = select(Dataset).where(Dataset.dataset_id == dataset_id)
    res = await db.execute(stmt)
    dataset = res.scalar_one_or_none()

    if not dataset:
        return create_error_response(
            req_id, status.HTTP_404_NOT_FOUND, "DATASET_NOT_FOUND", f"Dataset {dataset_id} not found"
        )

    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
    meta = ResponseMeta(
        rdkit_version=rdkit.__version__,
        pipeline_version=settings.PIPELINE_VERSION,
        timestamp=datetime.now(timezone.utc).isoformat(),
        duration_ms=duration_ms,
    )

    data = DatasetResponse(
        dataset_id=dataset.dataset_id,
        source_id=dataset.source_id,
        name=dataset.name,
        version=dataset.version,
        description=dataset.description,
        record_count=dataset.record_count,
        created_at=dataset.created_at.isoformat(),
    )

    return ApiResponse(request_id=req_id, status="success", data=data, meta=meta)
