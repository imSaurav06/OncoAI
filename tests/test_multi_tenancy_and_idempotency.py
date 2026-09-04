"""
Integration tests for Multi-Tenancy Isolation, Credential-Bound Auth, and Ingestion Idempotency.
"""
import pytest
from fastapi import HTTPException
from sqlalchemy import select, func
from app.storage.database import AsyncSessionLocal
from app.models.compound import Compound
from app.models.source import Source, Dataset, SourceRecord
from app.models.bioactivity import Bioactivity
from app.deduplication.entity_resolver import entity_resolver
from app.indexing.query_planner import query_planner
from app.jobs.tasks import run_ingestion_task
from app.ingestion.inhouse_adapter import InHouseExperimentAdapter
from app.security.auth import verify_api_key, register_tenant_api_key, clear_key_registry, TenantContext
from app.config.settings import settings
from app.storage.upsert import atomic_insert_on_conflict_do_nothing
import uuid


@pytest.mark.asyncio
async def test_tenant_isolation_database_layer():
    """Verify that Tenant B cannot query Tenant A's private compounds or bioactivities."""
    async with AsyncSessionLocal() as session:
        # Create proprietary compound for Tenant A
        comp_a, is_new, _ = await entity_resolver.resolve_or_create_compound(
            db=session,
            raw_smiles="CC(=O)Nc1ccc(O)cc1",  # Acetaminophen analog
            identifiers=[{"identifier_type": "PROPRIETARY_CODE", "identifier_value": "PHARMA_A_LEAD_001"}],
            tenant_id="tenant_pharma_a",
        )
        await session.commit()

        # Tenant B queries compounds
        results_b, total_b = await query_planner.search_compounds(
            db=session,
            identifier="PHARMA_A_LEAD_001",
            tenant_id="tenant_biotech_b",
            is_admin=False,
        )
        assert total_b == 0
        assert len(results_b) == 0

        # Tenant A queries their own compounds
        results_a, total_a = await query_planner.search_compounds(
            db=session,
            identifier="PHARMA_A_LEAD_001",
            tenant_id="tenant_pharma_a",
            is_admin=False,
        )
        assert total_a == 1
        assert len(results_a) == 1
        assert results_a[0]["compound_id"] == comp_a.compound_id

        # Admin can view across tenants
        results_admin, total_admin = await query_planner.search_compounds(
            db=session,
            identifier="PHARMA_A_LEAD_001",
            tenant_id="admin",
            is_admin=True,
        )
        assert total_admin == 1


@pytest.mark.asyncio
async def test_tenant_auth_credential_binding():
    """Verify real credential-derived tenant identity and anti-spoofing (403)."""
    clear_key_registry()

    # 1. Master Admin Key
    admin_ctx = await verify_api_key(header_key=settings.API_KEY, header_tenant=None)
    assert admin_ctx.is_admin is True
    assert admin_ctx.tenant_id is None

    # Admin specifying tenant scope
    admin_tenant_ctx = await verify_api_key(header_key=settings.API_KEY, header_tenant="client_corp")
    assert admin_tenant_ctx.is_admin is True
    assert admin_tenant_ctx.tenant_id == "client_corp"

    # 2. Structured Tenant Key: onco_sk_<tenant>_<token>
    tenant_key = "onco_sk_pharma_a_sec987654321"
    ctx = await verify_api_key(header_key=tenant_key, header_tenant=None)
    assert ctx.is_admin is False
    assert ctx.tenant_id == "pharma_a"

    # Matching header is accepted
    ctx_match = await verify_api_key(header_key=tenant_key, header_tenant="pharma_a")
    assert ctx_match.tenant_id == "pharma_a"
    assert ctx_match.is_admin is False

    # Header spoofing attempt (Tenant A key with Tenant B header): MUST RAISE 403
    with pytest.raises(HTTPException) as exc_info:
        await verify_api_key(header_key=tenant_key, header_tenant="biotech_b")
    assert exc_info.value.status_code == 403
    assert "Forbidden" in exc_info.value.detail

    # 3. Explicitly Registered Key
    register_tenant_api_key("custom_secret_key_123", "tenant_registered_client")
    reg_ctx = await verify_api_key(header_key="custom_secret_key_123", header_tenant=None)
    assert reg_ctx.tenant_id == "tenant_registered_client"
    assert reg_ctx.is_admin is False

    # Spoofing registered key raises 403
    with pytest.raises(HTTPException) as exc_spoof:
        await verify_api_key(header_key="custom_secret_key_123", header_tenant="other_tenant")
    assert exc_spoof.value.status_code == 403

    # 4. Invalid or missing credentials raise 401
    with pytest.raises(HTTPException) as exc_unauth:
        await verify_api_key(header_key="invalid_random_key")
    assert exc_unauth.value.status_code == 401


@pytest.mark.asyncio
async def test_tenant_safe_dataset_identity():
    """Verify that Tenant A and Tenant B ingesting the same version string get isolated dataset IDs."""
    adapter = InHouseExperimentAdapter()
    ver = f"v_shared_{uuid.uuid4().hex[:6]}"

    async with AsyncSessionLocal() as session:
        rep_a = await run_ingestion_task(
            db=session,
            source_adapter=adapter,
            dataset_name="Tenant A Assay Run",
            dataset_version=ver,
            raw_records_data=[{"experiment_id": "EXP_A_1", "smiles": "CC(=O)NC1CCCCC1", "target_gene": "EGFR", "ic50_nm": 10.0}],
            tenant_id="tenant_alpha",
        )
        rep_b = await run_ingestion_task(
            db=session,
            source_adapter=adapter,
            dataset_name="Tenant B Assay Run",
            dataset_version=ver,
            raw_records_data=[{"experiment_id": "EXP_B_1", "smiles": "CC(=O)NC1CCCC1", "target_gene": "EGFR", "ic50_nm": 20.0}],
            tenant_id="tenant_beta",
        )

        # Datasets must have distinct tenant-safe IDs
        ds_a_id = f"DS_tenant_alpha_{adapter.source_id}_{ver}".replace("-", "_")
        ds_b_id = f"DS_tenant_beta_{adapter.source_id}_{ver}".replace("-", "_")
        assert ds_a_id != ds_b_id

        ds_a = (await session.execute(select(Dataset).where(Dataset.dataset_id == ds_a_id))).scalar_one()
        ds_b = (await session.execute(select(Dataset).where(Dataset.dataset_id == ds_b_id))).scalar_one()
        assert ds_a.tenant_id == "tenant_alpha"
        assert ds_b.tenant_id == "tenant_beta"


@pytest.mark.asyncio
async def test_ingestion_idempotency_and_atomic_upsert():
    """Verify that re-running identical datasets executes atomic upsert without duplicates or collisions."""
    test_records = [
        {
            "experiment_id": "EXP_IDEMPOTENCY_ATOMIC_001",
            "smiles": "c1ccccc1NC(=O)C",
            "target_gene": "BRAF",
            "cell_line": "A375",
            "assay_type": "BINDING",
            "ic50_nm": 42.0,
            "relation": "=",
        }
    ]

    adapter = InHouseExperimentAdapter()
    dataset_name = "Idempotency Test Batch"
    dataset_version = f"v_idem_{uuid.uuid4().hex[:8]}"
    tenant_id = "tenant_test_idem"

    async with AsyncSessionLocal() as session:
        # First Run
        rep1 = await run_ingestion_task(
            db=session,
            source_adapter=adapter,
            dataset_name=dataset_name,
            dataset_version=dataset_version,
            raw_records_data=test_records,
            tenant_id=tenant_id,
        )
        assert rep1["valid_records"] == 1
        assert rep1["duplicate_records"] == 0

        # Count records after Run 1 (using tenant-safe dataset ID)
        ds_id = f"DS_{tenant_id}_{adapter.source_id}_{dataset_version}".replace("-", "_")
        count_sr_1 = (await session.execute(
            select(func.count(SourceRecord.source_record_id)).where(SourceRecord.dataset_id == ds_id)
        )).scalar_one()
        assert count_sr_1 == 1

        # Second Run with identical dataset: atomic upsert skips duplicate smoothly
        rep2 = await run_ingestion_task(
            db=session,
            source_adapter=adapter,
            dataset_name=dataset_name,
            dataset_version=dataset_version,
            raw_records_data=test_records,
            tenant_id=tenant_id,
        )
        assert rep2["valid_records"] == 1
        assert rep2["duplicate_records"] == 1

        # Count records after Run 2: MUST REMAIN EXACTLY 1
        count_sr_2 = (await session.execute(
            select(func.count(SourceRecord.source_record_id)).where(SourceRecord.dataset_id == ds_id)
        )).scalar_one()
        assert count_sr_2 == 1, "SourceRecord count should not increase on idempotent re-run!"
