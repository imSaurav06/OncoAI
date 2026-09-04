"""
Bioactivity API Endpoints (Section 40 of architecture).
"""
import time
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
import rdkit

from app.config.settings import settings
from app.storage.database import get_db
from app.security.auth import verify_api_key, TenantContext
from app.api.dependencies import get_request_id
from app.schemas.envelope import ApiResponse, ResponseMeta
from app.schemas.bioactivity import (
    BioactivitySearchRequest,
    BioactivitySearchResponse,
    BioactivityItem,
)
from app.indexing.query_planner import query_planner

router = APIRouter(prefix="/bioactivity", tags=["Bioactivity"])


@router.post(
    "/search",
    response_model=ApiResponse[BioactivitySearchResponse],
    summary="Search bioactivity observations",
    description="Faceted search across compound, target, cell line, activity type, and normalized potency ranges.",
)
async def search_bioactivity(
    payload: BioactivitySearchRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth: TenantContext = Depends(verify_api_key),
):
    req_id = get_request_id(request)
    start_time = time.perf_counter()

    items, total = await query_planner.search_bioactivity(
        db=db,
        compound_id=payload.compound_id,
        target_id=payload.target_id,
        gene_symbol=payload.gene_symbol,
        cell_line=payload.cell_line,
        activity_type=payload.activity_type,
        min_normalized_value=payload.min_normalized_value,
        max_normalized_value=payload.max_normalized_value,
        min_p_activity=payload.min_p_activity,
        is_censored=payload.is_censored,
        is_approximate=payload.is_approximate,
        is_experimental=payload.is_experimental,
        source_id=payload.source_id,
        tenant_id=auth.tenant_id,
        is_admin=auth.is_admin,
        limit=payload.limit,
        offset=payload.offset,
    )

    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
    meta = ResponseMeta(
        rdkit_version=rdkit.__version__,
        pipeline_version=settings.PIPELINE_VERSION,
        timestamp=datetime.now(timezone.utc).isoformat(),
        duration_ms=duration_ms,
        pagination={"total": total, "limit": payload.limit, "offset": payload.offset},
    )

    data = BioactivitySearchResponse(
        items=[BioactivityItem(**it) for it in items],
        total_count=total,
        limit=payload.limit,
        offset=payload.offset,
    )

    return ApiResponse(request_id=req_id, status="success", data=data, meta=meta)
