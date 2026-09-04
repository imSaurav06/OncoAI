"""
Job Task Implementations (Section 19 of architecture).
Handles ingestion, bulk standardization, and indexing jobs.
"""
from typing import Dict, Any, List, Optional
import json
import uuid
import hashlib
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.source import Source, Dataset, SourceRecord
from app.models.bioactivity import Target, CellLine, Assay, Bioactivity
from app.models.provenance import ProcessingRun
from app.deduplication.entity_resolver import entity_resolver
from app.normalization.units import normalize_bioactivity
from app.quality.qc_report import QualityAuditor
from app.storage.parquet_store import get_parquet_lake
from app.indexing.similarity import similarity_index
from app.chemistry.pipeline import ChemistryPipelineError
import rdkit


async def run_ingestion_task(
    db: AsyncSession,
    source_adapter,
    dataset_name: str,
    dataset_version: str,
    raw_records_data: List[Dict[str, Any]],
    tenant_id: Optional[str] = None,
    progress_callback=None
) -> Dict[str, Any]:
    """
    Executes end-to-end ingestion with idempotent deduplication and tenant isolation:
    1. Archives raw payload into Layer A (Object Store)
    2. Registers Source & Dataset metadata with tenant context
    3. Idempotently queries or inserts SourceRecords
    4. Iterates over records with RDKit standardization, entity deduplication,
       unit normalization, and QC tracking
    5. Writes processed batch into Layer B (Parquet lake)
    6. Returns execution and QC summary
    """
    auditor = QualityAuditor()
    parquet_lake = get_parquet_lake()

    # Step 1: Ensure Source exists
    src_stmt = select(Source).where(Source.source_id == source_adapter.source_id)
    res = await db.execute(src_stmt)
    source = res.scalar_one_or_none()
    if not source:
        source = Source(
            source_id=source_adapter.source_id,
            name=source_adapter.source_name,
            source_type=source_adapter.source_type,
            acquisition_method="ADAPTER_INGEST",
        )
        db.add(source)
        await db.flush()

    # Step 2: Ensure Dataset exists
    dataset_id = f"DS_{source_adapter.source_id}_{dataset_version}".replace("-", "_")
    ds_stmt = select(Dataset).where(Dataset.dataset_id == dataset_id)
    res = await db.execute(ds_stmt)
    dataset = res.scalar_one_or_none()
    if not dataset:
        dataset = Dataset(
            dataset_id=dataset_id,
            source_id=source.source_id,
            name=dataset_name,
            version=dataset_version,
            tenant_id=tenant_id,
            record_count=0,
        )
        db.add(dataset)
        await db.flush()

    # Step 3: Archive raw payload to Object Store (Layer A)
    raw_bytes = json.dumps(raw_records_data).encode("utf-8")
    raw_uri, payload_hash = source_adapter.archive_raw_payload(dataset_version, raw_bytes)

    # Step 4: Parse intermediate records via adapter
    parsed_records = source_adapter.parse_records(raw_records_data)
    total = len(parsed_records)

    # Create processing run audit record
    run_record = ProcessingRun(
        run_id=auditor.run_id,
        dataset_id=dataset_id,
        pipeline_version=auditor.metrics.total_records,  # will update upon completion
        rdkit_version=rdkit.__version__,
        status="RUNNING",
        total_records=total,
    )
    db.add(run_record)
    await db.flush()

    parquet_compounds: List[Dict[str, Any]] = []
    parquet_bioactivities: List[Dict[str, Any]] = []

    for idx, prec in enumerate(parsed_records):
        # Deterministic source record ID derived from (dataset_id, external_id)
        content_key = f"{dataset_id}:{prec.external_id}"
        src_rec_id = f"SR_{hashlib.sha256(content_key.encode()).hexdigest()[:16].upper()}"

        # Idempotency check: check if SourceRecord already exists
        sr_stmt = select(SourceRecord).where(
            SourceRecord.dataset_id == dataset_id,
            SourceRecord.external_id == prec.external_id
        )
        sr_res = await db.execute(sr_stmt)
        existing_sr = sr_res.scalar_one_or_none()

        if existing_sr:
            source_record = existing_sr
            is_new_record = False
        else:
            source_record = SourceRecord(
                source_record_id=src_rec_id,
                source_id=source.source_id,
                dataset_id=dataset_id,
                tenant_id=tenant_id,
                external_id=prec.external_id,
                raw_payload_uri=raw_uri,
                content_hash=payload_hash,
                raw_structure_string=prec.raw_structure_string,
                status="INGESTED",
            )
            db.add(source_record)
            await db.flush()
            is_new_record = True

        # Chemical standardization and deduplication
        compound = None
        analysis = None
        if prec.raw_structure_string:
            try:
                compound, is_new, analysis = await entity_resolver.resolve_or_create_compound(
                    db=db,
                    raw_smiles=prec.raw_structure_string,
                    identifiers=prec.identifiers,
                    source_record_id=source_record.source_record_id,
                    tenant_id=tenant_id,
                )
                auditor.record_success(
                    is_duplicate=(not is_new_record),
                    was_modified=analysis.standardization.was_modified,
                    salt_stripped=analysis.standardization.salt_removed,
                    charge_neutralized=analysis.standardization.charge_neutralized,
                )
                
                # Update in-memory similarity index
                similarity_index.index_compound(compound.compound_id, analysis.fingerprint_hex)

                parquet_compounds.append({
                    "compound_id": compound.compound_id,
                    "canonical_smiles": compound.canonical_smiles,
                    "inchikey": compound.inchikey,
                    "molecular_weight": compound.molecular_weight,
                    "clogp": analysis.descriptors["clogp"],
                    "tpsa": analysis.descriptors["tpsa"],
                    "morgan_fp_2048_hex": analysis.fingerprint_hex,
                })

            except ChemistryPipelineError as chem_err:
                await auditor.log_rejection_to_db(
                    db=db,
                    source_record_id=src_rec_id,
                    category=chem_err.code,
                    raw_snippet=prec.raw_structure_string,
                    error_message=chem_err.message,
                )
            except Exception as ex:
                await auditor.log_rejection_to_db(
                    db=db,
                    source_record_id=src_rec_id,
                    category="UNEXPECTED_ERROR",
                    raw_snippet=prec.raw_structure_string,
                    error_message=str(ex),
                )

        # Process bioactivity observations if compound is valid
        if compound and prec.bioactivity_payloads:
            prov = await auditor.create_provenance(db, source_record.source_record_id)
            for b_pay in prec.bioactivity_payloads:
                # Ensure Target exists
                target_id = b_pay.get("target_id") or "TGT_GENERAL"
                t_stmt = select(Target).where(Target.target_id == target_id)
                t_res = await db.execute(t_stmt)
                target = t_res.scalar_one_or_none()
                if not target:
                    target = Target(
                        target_id=target_id,
                        target_name=b_pay.get("target_name") or target_id,
                        target_type="PROTEIN",
                        gene_symbol=b_pay.get("gene_symbol"),
                    )
                    db.add(target)
                    await db.flush()

                # Ensure CellLine exists if present
                cell_line_id = None
                if b_pay.get("cell_line"):
                    cl_name = b_pay["cell_line"].strip()
                    cl_id = f"CL_{cl_name.upper().replace(' ', '_')}"
                    cl_stmt = select(CellLine).where(CellLine.cell_line_id == cl_id)
                    cl_res = await db.execute(cl_stmt)
                    cell_line = cl_res.scalar_one_or_none()
                    if not cell_line:
                        cell_line = CellLine(
                            cell_line_id=cl_id,
                            name=cl_name,
                        )
                        db.add(cell_line)
                        await db.flush()
                    cell_line_id = cl_id

                # Ensure Assay exists
                assay_name = b_pay.get("assay_name", f"Assay for {target_id}")
                assay_id = f"ASY_{target_id}_{cell_line_id or 'BIO'}".replace("-", "_")
                asy_stmt = select(Assay).where(Assay.assay_id == assay_id)
                asy_res = await db.execute(asy_stmt)
                assay = asy_res.scalar_one_or_none()
                if not assay:
                    assay = Assay(
                        assay_id=assay_id,
                        assay_name=assay_name,
                        assay_type=b_pay.get("assay_type", "BINDING"),
                        target_id=target_id,
                        cell_line_id=cell_line_id,
                        tenant_id=tenant_id,
                    )
                    db.add(assay)
                    await db.flush()

                # Unit normalization
                norm = normalize_bioactivity(
                    value=b_pay["original_value"],
                    unit=b_pay["original_unit"],
                    relation=b_pay.get("original_relation", "="),
                    activity_type=b_pay.get("activity_type", "IC50"),
                    molecular_weight=compound.molecular_weight,
                )
                if norm.is_outlier:
                    auditor.record_activity_outlier()

                # Deterministic bioactivity ID to enforce ingestion idempotency
                b_key = f"{compound.compound_id}:{assay_id}:{b_pay.get('activity_type', 'IC50')}:{source_record.source_record_id}"
                b_id = f"ACT_{hashlib.sha256(b_key.encode()).hexdigest()[:16].upper()}"

                # Check if Bioactivity already exists
                b_stmt = select(Bioactivity).where(Bioactivity.bioactivity_id == b_id)
                b_res = await db.execute(b_stmt)
                existing_bioact = b_res.scalar_one_or_none()

                if not existing_bioact:
                    bioactivity = Bioactivity(
                        bioactivity_id=b_id,
                        compound_id=compound.compound_id,
                        assay_id=assay_id,
                        source_record_id=source_record.source_record_id,
                        provenance_id=prov.provenance_id,
                        tenant_id=tenant_id,
                        is_experimental=b_pay.get("is_experimental", False),
                        activity_type=b_pay.get("activity_type", "IC50"),
                        original_relation=norm.original_relation,
                        original_value=norm.original_value,
                        original_unit=norm.original_unit,
                        normalized_relation=norm.normalized_relation,
                        normalized_value=norm.normalized_value,
                        normalized_unit=norm.normalized_unit,
                        p_activity=norm.p_activity,
                        p_activity_relation=norm.p_activity_relation,
                        is_censored=norm.is_censored,
                    )
                    db.add(bioactivity)

                    parquet_bioactivities.append({
                        "bioactivity_id": bioactivity.bioactivity_id,
                        "compound_id": compound.compound_id,
                        "target_id": target_id,
                        "tenant_id": tenant_id,
                        "activity_type": bioactivity.activity_type,
                        "normalized_value": bioactivity.normalized_value,
                        "normalized_unit": bioactivity.normalized_unit,
                        "p_activity": bioactivity.p_activity,
                        "p_activity_relation": bioactivity.p_activity_relation,
                        "is_censored": bioactivity.is_censored,
                        "is_experimental": bioactivity.is_experimental,
                    })

        # Report progress callback
        if progress_callback and (idx + 1) % 5 == 0:
            pct = round(((idx + 1) / total) * 100.0, 1)
            await progress_callback(pct)

    # Persist Parquet files (Layer B)
    if parquet_compounds:
        parquet_lake.write_compounds(parquet_compounds, partition_key=dataset_id)
    if parquet_bioactivities:
        parquet_lake.write_bioactivities(parquet_bioactivities, dataset_id=dataset_id)

    # Finalize ProcessingRun and Dataset counts
    dataset.record_count += auditor.metrics.valid_records
    run_record.status = "COMPLETED"
    run_record.pipeline_version = auditor.generate_report()["pipeline_version"]
    run_record.valid_records = auditor.metrics.valid_records
    run_record.rejected_records = auditor.metrics.rejected_records
    run_record.duplicate_records = auditor.metrics.duplicate_records
    run_record.completed_at = datetime.now(timezone.utc)

    await db.commit()
    return auditor.generate_report()
