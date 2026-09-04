"""
Integration tests for Multi-Tenancy Isolation and Ingestion Idempotency.
"""
import pytest
from sqlalchemy import select, func
from app.storage.database import AsyncSessionLocal
from app.models.compound import Compound
from app.models.source import Source, Dataset, SourceRecord
from app.models.bioactivity import Bioactivity
from app.deduplication.entity_resolver import entity_resolver
from app.indexing.query_planner import query_planner
from app.jobs.tasks import run_ingestion_task
from app.ingestion.inhouse_adapter import InHouseExperimentAdapter


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
async def test_ingestion_idempotency():
    """Verify that re-running the exact same ingestion dataset does not create duplicate records."""
    test_records = [
        {
            "experiment_id": "EXP_IDEMPOTENCY_001",
            "smiles": "c1ccccc1NC(=O)C",
            "target_gene": "BRAF",
            "cell_line": "A375",
            "assay_type": "BINDING",
            "ic50_nm": 42.0,
            "relation": "=",
        }
    ]

    adapter = InHouseExperimentAdapter()
    import uuid
    dataset_name = "Idempotency Test Batch"
    dataset_version = f"v_idem_{uuid.uuid4().hex[:8]}"

    async with AsyncSessionLocal() as session:
        # First Run
        rep1 = await run_ingestion_task(
            db=session,
            source_adapter=adapter,
            dataset_name=dataset_name,
            dataset_version=dataset_version,
            raw_records_data=test_records,
            tenant_id="tenant_test_idem",
        )
        assert rep1["valid_records"] == 1
        assert rep1["duplicate_records"] == 0

        # Count records after Run 1
        ds_id = f"DS_{adapter.source_id}_{dataset_version}".replace("-", "_")
        count_sr_1 = (await session.execute(
            select(func.count(SourceRecord.source_record_id)).where(SourceRecord.dataset_id == ds_id)
        )).scalar_one()
        assert count_sr_1 == 1

        # Second Run with identical dataset
        rep2 = await run_ingestion_task(
            db=session,
            source_adapter=adapter,
            dataset_name=dataset_name,
            dataset_version=dataset_version,
            raw_records_data=test_records,
            tenant_id="tenant_test_idem",
        )
        assert rep2["valid_records"] == 1
        assert rep2["duplicate_records"] == 1

        # Count records after Run 2: MUST NOT DOUBLE
        count_sr_2 = (await session.execute(
            select(func.count(SourceRecord.source_record_id)).where(SourceRecord.dataset_id == ds_id)
        )).scalar_one()
        assert count_sr_2 == 1, "SourceRecord count should not increase on idempotent re-run!"
