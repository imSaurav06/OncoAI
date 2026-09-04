"""
Chemistry & Compound API Endpoints (Section 40 of architecture).
"""
import time
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
import rdkit

from app.config.settings import settings
from app.storage.database import get_db
from app.security.auth import verify_api_key, TenantContext
from app.api.dependencies import get_request_id
from app.api.middleware import create_error_response
from app.schemas.envelope import ApiResponse, ResponseMeta
from app.schemas.compound import (
    AnalyzeRequest,
    AnalyzeResponse,
    StandardizeRequest,
    StandardizeResponse,
    CompoundDetailResponse,
    MolecularDescriptors,
    CompoundIdentifierItem,
)
from app.schemas.search import (
    CompoundSearchRequest,
    CompoundSearchResponse,
    SimilaritySearchRequest,
    SimilaritySearchResponse,
)
from app.chemistry.pipeline import chemistry_pipeline, ChemistryPipelineError
from app.indexing.query_planner import query_planner
from app.models.compound import Compound, ChemicalStructure, MolecularFeature, CompoundIdentifier
from app.models.bioactivity import Bioactivity
from app.models.source import SourceRecord

router = APIRouter(prefix="/compounds", tags=["Compounds & Chemistry"])


@router.post(
    "/analyze",
    response_model=ApiResponse[AnalyzeResponse],
    summary="Analyze chemical structure",
    description="Standardizes input SMILES and calculates Lipinski/Veber descriptors, Murcko scaffold, and Morgan fingerprint.",
)
async def analyze_compound(
    payload: AnalyzeRequest,
    request: Request,
    _: str = Depends(verify_api_key),
):
    req_id = get_request_id(request)
    start_time = time.perf_counter()

    try:
        res = chemistry_pipeline.analyze(payload.smiles)
    except ChemistryPipelineError as err:
        return create_error_response(req_id, status.HTTP_422_UNPROCESSABLE_ENTITY, err.code, err.message)

    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
    meta = ResponseMeta(
        rdkit_version=res.rdkit_version,
        pipeline_version=res.pipeline_version,
        timestamp=datetime.now(timezone.utc).isoformat(),
        duration_ms=duration_ms,
    )

    data = AnalyzeResponse(
        canonical_smiles=res.standardization.canonical_smiles,
        isomeric_smiles=res.standardization.isomeric_smiles,
        inchikey=res.standardization.inchikey,
        inchi=res.standardization.inchi,
        has_stereochemistry=res.standardization.has_stereochemistry,
        murcko_scaffold_smiles=res.murcko_scaffold,
        descriptors=MolecularDescriptors(**res.descriptors),
        fingerprint_summary={
            "n_bits": 2048,
            "on_bits_count": res.fingerprint_on_bits,
        },
        fingerprint_hex=res.fingerprint_hex,
        was_standardized=res.standardization.was_modified,
    )

    return ApiResponse(
        request_id=req_id,
        status="success",
        data=data,
        meta=meta,
    )


@router.post(
    "/standardize",
    response_model=ApiResponse[StandardizeResponse],
    summary="Standardize chemical structure",
    description="Performs deterministic standardization, salt stripping, and InChIKey generation.",
)
async def standardize_compound(
    payload: StandardizeRequest,
    request: Request,
    _: str = Depends(verify_api_key),
):
    req_id = get_request_id(request)
    start_time = time.perf_counter()

    try:
        res = chemistry_pipeline.standardize(payload.smiles)
    except ChemistryPipelineError as err:
        return create_error_response(req_id, status.HTTP_422_UNPROCESSABLE_ENTITY, err.code, err.message)

    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
    meta = ResponseMeta(
        rdkit_version=rdkit.__version__,
        pipeline_version=settings.PIPELINE_VERSION,
        timestamp=datetime.now(timezone.utc).isoformat(),
        duration_ms=duration_ms,
    )

    data = StandardizeResponse(
        canonical_smiles=res.canonical_smiles,
        inchikey=res.inchikey,
        inchi=res.inchi,
        status="valid",
        was_modified=res.was_modified,
        salt_removed=res.salt_removed,
        charge_neutralized=res.charge_neutralized,
        salt_fragment_smiles=res.salt_fragment_smiles,
    )

    return ApiResponse(
        request_id=req_id,
        status="success",
        data=data,
        meta=meta,
    )


@router.get(
    "/{compound_id}",
    response_model=ApiResponse[CompoundDetailResponse],
    summary="Get compound details by ID",
)
async def get_compound_by_id(
    compound_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth: TenantContext = Depends(verify_api_key),
):
    req_id = get_request_id(request)
    start_time = time.perf_counter()

    stmt = (
        select(Compound)
        .where(Compound.compound_id == compound_id)
        .options(
            selectinload(Compound.structure),
            selectinload(Compound.features),
            selectinload(Compound.identifiers),
        )
    )
    res = await db.execute(stmt)
    comp = res.scalar_one_or_none()

    # Multi-tenant isolation: hide private compounds from other tenants
    if not comp or (not auth.is_admin and comp.tenant_id is not None and comp.tenant_id != auth.tenant_id):
        return create_error_response(
            req_id, status.HTTP_404_NOT_FOUND, "COMPOUND_NOT_FOUND", f"Compound {compound_id} not found"
        )

    # Activity count
    act_stmt = select(func.count(Bioactivity.bioactivity_id)).where(Bioactivity.compound_id == compound_id)
    if not auth.is_admin:
        if auth.tenant_id:
            act_stmt = act_stmt.where(or_(Bioactivity.tenant_id.is_(None), Bioactivity.tenant_id == auth.tenant_id))
        else:
            act_stmt = act_stmt.where(Bioactivity.tenant_id.is_(None))
    act_count_res = await db.execute(act_stmt)
    act_count = act_count_res.scalar_one() or 0

    # Source count
    src_stmt = select(func.count(SourceRecord.source_record_id)).where(SourceRecord.compound_id == compound_id)
    src_count_res = await db.execute(src_stmt)
    src_count = src_count_res.scalar_one() or 0

    descriptors = None
    if comp.features and comp.structure:
        descriptors = MolecularDescriptors(
            molecular_weight=comp.molecular_weight,
            exact_mass=comp.exact_mass,
            molecular_formula=comp.molecular_formula,
            heavy_atom_count=comp.heavy_atom_count,
            formal_charge=comp.formal_charge,
            clogp=comp.features.clogp,
            tpsa=comp.features.tpsa,
            hbd=comp.features.hbd,
            hba=comp.features.hba,
            rotatable_bonds=comp.features.rotatable_bonds,
            fraction_csp3=comp.features.fraction_csp3,
            num_rings=comp.structure.num_rings,
            num_aromatic_rings=comp.structure.num_aromatic_rings,
            num_aliphatic_rings=comp.structure.num_aliphatic_rings,
            num_chiral_centers=comp.structure.num_chiral_centers,
        )

    identifiers = [
        CompoundIdentifierItem(
            identifier_type=ident.identifier_type,
            identifier_value=ident.identifier_value,
            source_id=ident.source_id,
        )
        for ident in comp.identifiers
        if auth.is_admin or ident.tenant_id is None or ident.tenant_id == auth.tenant_id
    ]

    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
    meta = ResponseMeta(
        rdkit_version=comp.rdkit_version,
        pipeline_version=comp.processing_version,
        timestamp=datetime.now(timezone.utc).isoformat(),
        duration_ms=duration_ms,
    )

    data = CompoundDetailResponse(
        compound_id=comp.compound_id,
        canonical_smiles=comp.canonical_smiles,
        isomeric_smiles=comp.isomeric_smiles,
        inchikey=comp.inchikey,
        inchi=comp.inchi,
        has_stereochemistry=comp.has_stereochemistry,
        molecular_formula=comp.molecular_formula,
        molecular_weight=comp.molecular_weight,
        exact_mass=comp.exact_mass,
        heavy_atom_count=comp.heavy_atom_count,
        formal_charge=comp.formal_charge,
        murcko_scaffold_smiles=comp.murcko_scaffold_smiles,
        processing_version=comp.processing_version,
        rdkit_version=comp.rdkit_version,
        created_at=comp.created_at.isoformat(),
        descriptors=descriptors,
        identifiers=identifiers,
        bioactivity_count=act_count,
        source_count=src_count,
    )

    return ApiResponse(request_id=req_id, status="success", data=data, meta=meta)


@router.post(
    "/search",
    response_model=ApiResponse[CompoundSearchResponse],
    summary="Search compounds by attributes, scaffold, or substructure",
)
async def search_compounds(
    payload: CompoundSearchRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth: TenantContext = Depends(verify_api_key),
):
    req_id = get_request_id(request)
    start_time = time.perf_counter()

    try:
        items, total = await query_planner.search_compounds(
            db=db,
            exact_inchikey=payload.exact_inchikey,
            substructure_smiles=payload.substructure_smiles,
            min_mw=payload.min_mw,
            max_mw=payload.max_mw,
            min_clogp=payload.min_clogp,
            max_clogp=payload.max_clogp,
            min_tpsa=payload.min_tpsa,
            max_tpsa=payload.max_tpsa,
            scaffold_smiles=payload.scaffold_smiles,
            molecular_formula=payload.molecular_formula,
            identifier=payload.identifier,
            tenant_id=auth.tenant_id,
            is_admin=auth.is_admin,
            limit=payload.limit,
            offset=payload.offset,
        )
    except ValueError as err:
        return create_error_response(req_id, status.HTTP_400_BAD_REQUEST, "INVALID_QUERY", str(err))

    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
    meta = ResponseMeta(
        rdkit_version=rdkit.__version__,
        pipeline_version=settings.PIPELINE_VERSION,
        timestamp=datetime.now(timezone.utc).isoformat(),
        duration_ms=duration_ms,
        pagination={"total": total, "limit": payload.limit, "offset": payload.offset},
    )

    data = CompoundSearchResponse(
        items=items,
        total_count=total,
        limit=payload.limit,
        offset=payload.offset,
    )

    return ApiResponse(request_id=req_id, status="success", data=data, meta=meta)


@router.post(
    "/similarity",
    response_model=ApiResponse[SimilaritySearchResponse],
    summary="Molecular similarity search",
    description="Computes Morgan/ECFP4 Tanimoto similarity over indexed compounds with optional bioactivity constraints.",
)
async def search_similarity(
    payload: SimilaritySearchRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    auth: TenantContext = Depends(verify_api_key),
):
    req_id = get_request_id(request)
    start_time = time.perf_counter()

    try:
        res = await query_planner.search_similarity(
            db=db,
            query_smiles=payload.smiles,
            threshold=payload.threshold,
            limit=payload.limit,
            target_id=payload.target_id,
            activity_type=payload.activity_type,
            max_activity_nm=payload.max_activity_nm,
            tenant_id=auth.tenant_id,
            is_admin=auth.is_admin,
        )
    except ChemistryPipelineError as err:
        return create_error_response(req_id, status.HTTP_422_UNPROCESSABLE_ENTITY, err.code, err.message)

    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
    meta = ResponseMeta(
        rdkit_version=rdkit.__version__,
        pipeline_version=settings.PIPELINE_VERSION,
        timestamp=datetime.now(timezone.utc).isoformat(),
        duration_ms=duration_ms,
    )

    data = SimilaritySearchResponse(**res)
    return ApiResponse(request_id=req_id, status="success", data=data, meta=meta)
