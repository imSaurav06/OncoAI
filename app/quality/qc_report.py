"""
Automated Data Quality (QC) and Scientific Provenance Auditor (Sections 11 & 26 of architecture).
"""
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from app.models.provenance import ProcessingRun, Provenance, RejectedRecord
from app.config.settings import settings
import rdkit


@dataclass
class QualityMetrics:
    total_records: int = 0
    valid_records: int = 0
    rejected_records: int = 0
    duplicate_records: int = 0
    salt_stripped_count: int = 0
    charge_neutralized_count: int = 0
    outlier_activities_count: int = 0
    rejection_breakdown: Dict[str, int] = field(default_factory=dict)


class QualityAuditor:
    """
    Tracks data quality metrics during ingestion/processing runs
    and persists audit logs and rejected records.
    """

    def __init__(self, run_id: Optional[str] = None):
        self.run_id = run_id or f"RUN_{uuid.uuid4().hex[:10].upper()}"
        self.metrics = QualityMetrics()
        self.start_time = datetime.now(timezone.utc)

    def record_success(self, is_duplicate: bool = False, was_modified: bool = False, salt_stripped: bool = False, charge_neutralized: bool = False):
        self.metrics.total_records += 1
        self.metrics.valid_records += 1
        if is_duplicate:
            self.metrics.duplicate_records += 1
        if salt_stripped:
            self.metrics.salt_stripped_count += 1
        if charge_neutralized:
            self.metrics.charge_neutralized_count += 1

    def record_rejection(self, category: str):
        self.metrics.total_records += 1
        self.metrics.rejected_records += 1
        self.metrics.rejection_breakdown[category] = self.metrics.rejection_breakdown.get(category, 0) + 1

    def record_activity_outlier(self):
        self.metrics.outlier_activities_count += 1

    async def log_rejection_to_db(
        self,
        db: AsyncSession,
        source_record_id: Optional[str],
        category: str,
        raw_snippet: Optional[str],
        error_message: str
    ) -> RejectedRecord:
        """Persists explicit rejection record with full scientific traceability."""
        rejection = RejectedRecord(
            rejection_id=f"REJ_{uuid.uuid4().hex[:10].upper()}",
            source_record_id=source_record_id,
            rejection_category=category,
            raw_data_snippet=raw_snippet[:1000] if raw_snippet else None,
            error_message=error_message,
            pipeline_version=settings.PIPELINE_VERSION,
            rdkit_version=rdkit.__version__,
        )
        db.add(rejection)
        self.record_rejection(category)
        return rejection

    async def create_provenance(
        self,
        db: AsyncSession,
        source_record_id: Optional[str]
    ) -> Provenance:
        """Generates a verifiable provenance seal for a processed datum."""
        prov = Provenance(
            provenance_id=f"PRV_{uuid.uuid4().hex[:12].upper()}",
            source_record_id=source_record_id,
            processing_run_id=self.run_id,
            pipeline_version=settings.PIPELINE_VERSION,
            rdkit_version=rdkit.__version__,
            normalization_version="norm-v1.0",
        )
        db.add(prov)
        return prov

    def generate_report(self) -> Dict[str, Any]:
        """Generates a complete JSON-serializable Data Quality summary."""
        total = self.metrics.total_records
        valid = self.metrics.valid_records
        validity_rate = (valid / total * 100.0) if total > 0 else 100.0
        duplicate_rate = (self.metrics.duplicate_records / total * 100.0) if total > 0 else 0.0

        return {
            "run_id": self.run_id,
            "pipeline_version": settings.PIPELINE_VERSION,
            "rdkit_version": rdkit.__version__,
            "total_records": total,
            "valid_records": valid,
            "rejected_records": self.metrics.rejected_records,
            "duplicate_records": self.metrics.duplicate_records,
            "validity_percentage": round(validity_rate, 2),
            "duplicate_percentage": round(duplicate_rate, 2),
            "salt_stripped_count": self.metrics.salt_stripped_count,
            "charge_neutralized_count": self.metrics.charge_neutralized_count,
            "outlier_activities_count": self.metrics.outlier_activities_count,
            "rejection_breakdown": self.metrics.rejection_breakdown,
            "started_at": self.start_time.isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
