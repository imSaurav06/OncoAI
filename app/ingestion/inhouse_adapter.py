"""
In-House Experimental Feedback & Wet-Lab Oncology Assay Adapter (Section 31 of architecture).
Distinguishes proprietary experimental measurements from public observations.
"""
from typing import List, Dict, Any
from app.ingestion.base import BaseSourceAdapter, RawIngestionRecord


class InHouseExperimentAdapter(BaseSourceAdapter):
    @property
    def source_id(self) -> str:
        return "SRC_INHOUSE_LAB"

    @property
    def source_name(self) -> str:
        return "OncoAI In-House Screening Laboratory"

    @property
    def source_type(self) -> str:
        return "EXPERIMENTAL"

    def validate_payload(self, raw_data: Any) -> bool:
        return isinstance(raw_data, list)

    def parse_records(self, raw_data: List[Dict[str, Any]]) -> List[RawIngestionRecord]:
        records = []
        for exp in raw_data:
            lab_compound_id = exp.get("internal_batch_id") or exp.get("external_id", "EXP_BATCH_001")
            smiles = exp.get("smiles")

            identifiers = [
                {"identifier_type": "EXTERNAL_ACCESSION", "identifier_value": lab_compound_id, "source_id": self.source_id}
            ]
            if exp.get("notebook_ref"):
                identifiers.append({
                    "identifier_type": "SYNONYM",
                    "identifier_value": exp["notebook_ref"],
                    "source_id": self.source_id
                })

            bioactivity = [{
                "target_id": exp.get("target_id", "TGT_EGFR"),
                "target_name": exp.get("target_name", "Epidermal Growth Factor Receptor"),
                "gene_symbol": exp.get("gene_symbol", "EGFR"),
                "cell_line": exp.get("cell_line", "A549"),
                "assay_name": exp.get("assay_name", "Kinase Glo Enzymatic Assay"),
                "assay_type": exp.get("assay_type", "BINDING"),
                "activity_type": exp.get("activity_type", "IC50"),
                "original_relation": exp.get("relation", "="),
                "original_value": float(exp.get("value", 10.0)),
                "original_unit": exp.get("unit", "nM"),
                "is_experimental": True,  # Critical: Distinguish experimental wet-lab from public observations
            }]

            records.append(
                RawIngestionRecord(
                    external_id=lab_compound_id,
                    raw_structure_string=smiles,
                    raw_payload=exp,
                    identifiers=identifiers,
                    bioactivity_payloads=bioactivity,
                )
            )
        return records
