"""
Storage Layer A (Raw Data Lake) - Object Store Abstraction.
Provides immutable storage for raw payloads with SHA-256 integrity verification.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Tuple
import hashlib
import json
import os
from pathlib import Path
from app.config.settings import settings


class BaseObjectStore(ABC):
    """Abstract interface for S3-compatible or local raw object lakes."""

    @abstractmethod
    def put_raw(self, key: str, data: bytes, metadata: Dict[str, Any]) -> Tuple[str, str]:
        """
        Store raw data immutably.
        Returns: (stored_uri, sha256_hash)
        """
        pass

    @abstractmethod
    def get_raw(self, key: str) -> Tuple[bytes, Dict[str, Any]]:
        """Retrieve raw payload and associated metadata."""
        pass

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Check if an object exists."""
        pass


class LocalObjectStore(BaseObjectStore):
    """Local filesystem object lake implementation with S3-like key paths."""

    def __init__(self, root_dir: Optional[Path] = None):
        self.root_dir = Path(root_dir or settings.STORAGE_LOCAL_ROOT)
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _get_paths(self, key: str) -> Tuple[Path, Path]:
        clean_key = key.lstrip("/").replace("\\", "/")
        obj_path = self.root_dir / clean_key
        meta_path = self.root_dir / f"{clean_key}.meta.json"
        return obj_path, meta_path

    def put_raw(self, key: str, data: bytes, metadata: Dict[str, Any]) -> Tuple[str, str]:
        obj_path, meta_path = self._get_paths(key)
        obj_path.parent.mkdir(parents=True, exist_ok=True)

        sha256 = hashlib.sha256(data).hexdigest()

        # If already exists with same content, verify immutability
        if obj_path.exists():
            existing_hash = hashlib.sha256(obj_path.read_bytes()).hexdigest()
            if existing_hash == sha256:
                return f"file://{obj_path.as_posix()}", sha256

        # Write immutable data
        obj_path.write_bytes(data)

        # Write metadata envelope
        full_metadata = {
            "key": key,
            "sha256": sha256,
            "size_bytes": len(data),
            **metadata
        }
        meta_path.write_text(json.dumps(full_metadata, indent=2), encoding="utf-8")

        return f"file://{obj_path.as_posix()}", sha256

    def get_raw(self, key: str) -> Tuple[bytes, Dict[str, Any]]:
        obj_path, meta_path = self._get_paths(key)
        if not obj_path.exists():
            raise FileNotFoundError(f"Raw object {key} not found in lake")
        
        data = obj_path.read_bytes()
        metadata = {}
        if meta_path.exists():
            metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            
        return data, metadata

    def exists(self, key: str) -> bool:
        obj_path, _ = self._get_paths(key)
        return obj_path.exists()


class S3ObjectStore(BaseObjectStore):
    """Production S3 / MinIO Object Lake."""

    def __init__(self):
        # Dynamically import boto3 if running with S3 configured
        try:
            import boto3
            from botocore.config import Config
        except ImportError:
            raise RuntimeError("boto3 must be installed to use S3ObjectStore")

        self.bucket_name = settings.S3_BUCKET_NAME
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT_URL,
            aws_access_key_id=settings.S3_ACCESS_KEY_ID,
            aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY,
            region_name=settings.S3_REGION_NAME,
            config=Config(signature_version="s3v4")
        )

    def put_raw(self, key: str, data: bytes, metadata: Dict[str, Any]) -> Tuple[str, str]:
        sha256 = hashlib.sha256(data).hexdigest()
        string_metadata = {k: str(v) for k, v in metadata.items()}
        string_metadata["sha256"] = sha256

        self.client.put_object(
            Bucket=self.bucket_name,
            Key=key,
            Body=data,
            Metadata=string_metadata
        )
        uri = f"s3://{self.bucket_name}/{key}"
        return uri, sha256

    def get_raw(self, key: str) -> Tuple[bytes, Dict[str, Any]]:
        resp = self.client.get_object(Bucket=self.bucket_name, Key=key)
        data = resp["Body"].read()
        metadata = resp.get("Metadata", {})
        return data, metadata

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket_name, Key=key)
            return True
        except Exception:
            return False


def get_object_store() -> BaseObjectStore:
    """Factory for selecting object store backend."""
    if settings.STORAGE_BACKEND == "s3" and settings.S3_BUCKET_NAME:
        return S3ObjectStore()
    return LocalObjectStore()
