"""
PubChem Compound and BioAssay Adapter.
"""
from typing import List, Dict, Any
from app.ingestion.base import BaseSourceAdapter, RawIngestionRecord


class PubChemAdapter(BaseSourceAdapter):
    @property
    def source_id(self) -> str:
        return "SRC_PUBCHEM"

    @property
    def source_name(self) -> str:
        return "PubChem"

    @property
    def source_type(self) -> str:
        return "PUBLIC_DATABASE"

    def validate_payload(self, raw_data: Any) -> bool:
        return isinstance(raw_data, list)

    def parse_records(self, raw_data: List[Dict[str, Any]]) -> List[RawIngestionRecord]:
        records = []
        for item in raw_data:
            cid = str(item.get("cid") or item.get("external_id", "UNKNOWN"))
            smiles = item.get("smiles") or item.get("canonical_smiles")

            identifiers = [
                {"identifier_type": "EXTERNAL_ACCESSION", "identifier_value": f"CID_{cid}", "source_id": self.source_id}
            ]
            if item.get("iupac_name"):
                identifiers.append({
                    "identifier_type": "IUPAC_NAME",
                    "identifier_value": item["iupac_name"],
                    "source_id": self.source_id
                })

            bioactivities = []
            if "bioassays" in item and isinstance(item["bioassays"], list):
                for assay in item["bioassays"]:
                    bioactivities.append({
                        "target_id": assay.get("target_id"),
                        "target_name": assay.get("target_name"),
                        "gene_symbol": assay.get("gene_symbol"),
                        "cell_line": assay.get("cell_line"),
                        "assay_name": assay.get("assay_name", "PubChem BioAssay"),
                        "assay_type": assay.get("assay_type", "FUNCTIONAL"),
                        "activity_type": assay.get("activity_type", "IC50"),
                        "original_relation": assay.get("relation", "="),
                        "original_value": float(assay.get("value", 0.0)),
                        "original_unit": assay.get("unit", "uM"),
                        "is_experimental": False,
                    })

            records.append(
                RawIngestionRecord(
                    external_id=f"CID_{cid}",
                    raw_structure_string=smiles,
                    raw_payload=item,
                    identifiers=identifiers,
                    bioactivity_payloads=bioactivities,
                )
            )
        return records
