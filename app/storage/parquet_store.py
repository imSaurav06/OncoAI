"""
Storage Layer B (Standardized Columnar Lake) - Parquet & DuckDB Query Engine.
Provides high-performance partitioned Parquet storage and columnar analytical querying.
"""
from typing import List, Dict, Any, Optional
from pathlib import Path
import uuid
import time
import pyarrow as pa
import pyarrow.parquet as pq
import duckdb
from app.config.settings import settings


class ParquetLake:
    """Manages Layer B standardized Parquet files and DuckDB analytical queries."""

    def __init__(self, lake_root: Optional[Path] = None):
        self.lake_root = Path(lake_root or settings.PARQUET_LAKE_PATH)
        self.compounds_dir = self.lake_root / "compounds"
        self.bioactivities_dir = self.lake_root / "bioactivities"
        
        self.compounds_dir.mkdir(parents=True, exist_ok=True)
        self.bioactivities_dir.mkdir(parents=True, exist_ok=True)

    def write_compounds(self, records: List[Dict[str, Any]], partition_key: str = "default") -> str:
        """Writes standardized compound records into a partitioned Parquet file."""
        if not records:
            return ""

        table = pa.Table.from_pylist(records)
        target_dir = self.compounds_dir / f"partition={partition_key}"
        target_dir.mkdir(parents=True, exist_ok=True)
        
        ts_hex = f"{int(time.time())}_{uuid.uuid4().hex[:6]}"
        file_path = target_dir / f"compounds_{len(records)}_{ts_hex}.parquet"
        pq.write_table(table, file_path, compression="snappy")
        return file_path.as_posix()

    def write_bioactivities(self, records: List[Dict[str, Any]], dataset_id: str) -> str:
        """Writes standardized bioactivity records partitioned by dataset_id."""
        if not records:
            return ""

        table = pa.Table.from_pylist(records)
        target_dir = self.bioactivities_dir / f"dataset={dataset_id}"
        target_dir.mkdir(parents=True, exist_ok=True)

        ts_hex = f"{int(time.time())}_{uuid.uuid4().hex[:6]}"
        file_path = target_dir / f"bioactivities_{len(records)}_{ts_hex}.parquet"
        pq.write_table(table, file_path, compression="snappy")
        return file_path.as_posix()

    def query(self, sql_query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Executes a SQL query over the Parquet lake using DuckDB.
        Table aliases 'compounds' and 'bioactivities' are automatically mapped.
        """
        con = duckdb.connect(database=":memory:")
        
        # Register views over parquet files if files exist
        compounds_glob = (self.compounds_dir / "**" / "*.parquet").as_posix()
        bioactivities_glob = (self.bioactivities_dir / "**" / "*.parquet").as_posix()

        # Check if any files exist before creating views
        has_compounds = len(list(self.compounds_dir.glob("**/*.parquet"))) > 0
        has_bioactivities = len(list(self.bioactivities_dir.glob("**/*.parquet"))) > 0

        if has_compounds:
            con.execute(f"CREATE VIEW compounds AS SELECT * FROM read_parquet('{compounds_glob}')")
        if has_bioactivities:
            con.execute(f"CREATE VIEW bioactivities AS SELECT * FROM read_parquet('{bioactivities_glob}')")

        try:
            res = con.execute(sql_query, params or {}).fetchall()
            cols = [desc[0] for desc in con.description]
            return [dict(zip(cols, row)) for row in res]
        finally:
            con.close()


def get_parquet_lake() -> ParquetLake:
    return ParquetLake()
