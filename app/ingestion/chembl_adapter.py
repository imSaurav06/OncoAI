"""
ChEMBL Public Bioactivity & Chemistry Adapter.
"""
from typing import List, Dict, Any
from app.ingestion.base import BaseSourceAdapter, RawIngestionRecord


class ChEMBLAdapter(BaseSourceAdapter):
    @property
    def source_id(self) -> str:
        return "SRC_CHEMBL"

    @property
    def source_name(self) -> str:
        return "ChEMBL Database"

    @property
    def source_type(self) -> str:
        return "PUBLIC_DATABASE"

    def validate_payload(self, raw_data: Any) -> bool:
        return isinstance(raw_data, list)

    def parse_records(self, raw_data: List[Dict[str, Any]]) -> List[RawIngestionRecord]:
        records = []
        for item in raw_data:
            chembl_id = item.get("molecule_chembl_id") or item.get("external_id", "UNKNOWN")
            smiles = item.get("canonical_smiles") or item.get("smiles")

            identifiers = [
                {"identifier_type": "EXTERNAL_ACCESSION", "identifier_value": chembl_id, "source_id": self.source_id}
            ]
            if item.get("pref_name"):
                identifiers.append({
                    "identifier_type": "TRADE_NAME",
                    "identifier_value": item["pref_name"],
                    "source_id": self.source_id
                })

            bioactivities = []
            if "activities" in item and isinstance(item["activities"], list):
                for act in item["activities"]:
                    bioactivities.append({
                        "target_id": act.get("target_id"),
                        "target_name": act.get("target_name"),
                        "gene_symbol": act.get("gene_symbol"),
                        "cell_line": act.get("cell_line"),
                        "assay_name": act.get("assay_name", "ChEMBL Bioassay"),
                        "assay_type": act.get("assay_type", "BINDING"),
                        "activity_type": act.get("standard_type") or act.get("activity_type", "IC50"),
                        "original_relation": act.get("standard_relation") or act.get("relation", "="),
                        "original_value": float(act.get("standard_value") or act.get("value", 0.0)),
                        "original_unit": act.get("standard_units") or act.get("unit", "nM"),
                        "is_experimental": False,
                    })

            records.append(
                RawIngestionRecord(
                    external_id=chembl_id,
                    raw_structure_string=smiles,
                    raw_payload=item,
                    identifiers=identifiers,
                    bioactivity_payloads=bioactivities,
                )
            )
        return records
