"""
Extensible Data Source Ingestion Framework (Section 16 of architecture).
Provides abstract base adapter for public and research data providers.
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import uuid

from app.storage.object_store import get_object_store


@dataclass
class RawIngestionRecord:
    external_id: str
    raw_structure_string: Optional[str]
    raw_payload: Dict[str, Any]
    identifiers: List[Dict[str, str]]
    bioactivity_payloads: List[Dict[str, Any]]


class BaseSourceAdapter(ABC):
    """
    Abstract adapter for source ingestion.
    Enforces decoupling between external formats and canonical models.
    """

    @property
    @abstractmethod
    def source_id(self) -> str:
        pass

    @property
    @abstractmethod
    def source_name(self) -> str:
        pass

    @property
    @abstractmethod
    def source_type(self) -> str:
        pass

    @abstractmethod
    def validate_payload(self, raw_data: Any) -> bool:
        pass

    @abstractmethod
    def parse_records(self, raw_data: Any) -> List[RawIngestionRecord]:
        """Parses source payload into standardized intermediate records."""
        pass

    def archive_raw_payload(self, dataset_version: str, raw_data_bytes: bytes) -> Tuple[str, str]:
        """
        Stores unaltered source payload in Layer A Raw Data Lake.
        Returns: (raw_payload_uri, sha256_hash)
        """
        store = get_object_store()
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        key = f"raw/{self.source_id}/{dataset_version}/{timestamp}_{uuid.uuid4().hex[:8]}.raw"
        metadata = {
            "source_id": self.source_id,
            "dataset_version": dataset_version,
            "ingested_at": datetime.now(timezone.utc).isoformat(),
        }
        return store.put_raw(key, raw_data_bytes, metadata)
