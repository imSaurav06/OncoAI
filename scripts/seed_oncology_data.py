"""
Realistic Oncology Chemistry & Bioactivity Data Seeder.
Populates standard oncology targets (EGFR, BRAF, KRAS, CDK4/6) and validated clinical inhibitors.
"""
import sys
from pathlib import Path

# Ensure app package is in Python search path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
import json
from app.storage.database import AsyncSessionLocal, init_db
from app.jobs.tasks import run_ingestion_task
from app.ingestion.chembl_adapter import ChEMBLAdapter
from app.ingestion.pubchem_adapter import PubChemAdapter
from app.ingestion.inhouse_adapter import InHouseExperimentAdapter


# Validated oncology compounds with diverse structures and targets
CHEMBL_ONCOLOGY_DATA = [
    {
        "molecule_chembl_id": "CHEMBL3353410",
        "pref_name": "Osimertinib",
        "canonical_smiles": "COc1cc(N(C)CCN(C)C)c(NC(=O)C=C)cc1Nc1nccc(n1)c1cn(C)c2ccccc12",
        "activities": [
            {
                "target_id": "TGT_EGFR",
                "target_name": "Epidermal Growth Factor Receptor (T790M mutant)",
                "gene_symbol": "EGFR",
                "cell_line": "H1975",
                "assay_name": "EGFR T790M Kinase Assay",
                "assay_type": "BINDING",
                "standard_type": "IC50",
                "standard_relation": "=",
                "standard_value": 1.2,
                "standard_units": "nM",
            },
            {
                "target_id": "TGT_EGFR",
                "target_name": "Epidermal Growth Factor Receptor",
                "gene_symbol": "EGFR",
                "cell_line": "PC-9",
                "assay_name": "PC-9 Cell Growth Inhibition",
                "assay_type": "CELL_GROWTH",
                "standard_type": "IC50",
                "standard_relation": "=",
                "standard_value": 15.0,
                "standard_units": "nM",
            }
        ]
    },
    {
        "molecule_chembl_id": "CHEMBL939",
        "pref_name": "Gefitinib",
        "canonical_smiles": "COc1cc2ncnc(Nc3ccc(F)c(Cl)c3)c2cc1OCCCN1CCOCC1",
        "activities": [
            {
                "target_id": "TGT_EGFR",
                "target_name": "Epidermal Growth Factor Receptor",
                "gene_symbol": "EGFR",
                "cell_line": "A549",
                "assay_name": "A549 Proliferation Assay",
                "assay_type": "CELL_GROWTH",
                "standard_type": "IC50",
                "standard_relation": "=",
                "standard_value": 33.0,
                "standard_units": "nM",
            }
        ]
    },
    {
        "molecule_chembl_id": "CHEMBL1229517",
        "pref_name": "Vemurafenib",
        "canonical_smiles": "CCCS(=O)(=O)Nc1ccc(F)c(C(=O)c2c[nH]c3ncc(-c4ccc(Cl)cc4)cc23)c1F",
        "activities": [
            {
                "target_id": "TGT_BRAF",
                "target_name": "Serine/threonine-protein kinase B-raf (V600E)",
                "gene_symbol": "BRAF",
                "cell_line": "A375",
                "assay_name": "BRAF V600E Enzymatic Assay",
                "assay_type": "BINDING",
                "standard_type": "IC50",
                "standard_relation": "=",
                "standard_value": 31.0,
                "standard_units": "nM",
            }
        ]
    },
    {
        "molecule_chembl_id": "CHEMBL4462719",
        "pref_name": "Sotorasib",
        "canonical_smiles": "CC(C)C1=C(C=C(C=C1Cl)F)C2=C(C(=NC3=C2N=C(N=C3O)N4CCN(CC4)C)NC(=O)C=C)F",
        "activities": [
            {
                "target_id": "TGT_KRAS",
                "target_name": "GTPase KRas (G12C mutant)",
                "gene_symbol": "KRAS",
                "cell_line": "H358",
                "assay_name": "KRAS G12C Covalent Binding Assay",
                "assay_type": "BINDING",
                "standard_type": "IC50",
                "standard_relation": "=",
                "standard_value": 1.8,
                "standard_units": "nM",
            }
        ]
    },
    {
        "molecule_chembl_id": "CHEMBL189963",
        "pref_name": "Palbociclib",
        "canonical_smiles": "CC(=O)c1c(C)c2cnc(Nc3ncc(cc3)N4CCNCC4)nc2n1C5CCCC5",
        "activities": [
            {
                "target_id": "TGT_CDK4",
                "target_name": "Cyclin-dependent kinase 4",
                "gene_symbol": "CDK4",
                "cell_line": "MCF-7",
                "assay_name": "CDK4 Kinase Assay",
                "assay_type": "BINDING",
                "standard_type": "IC50",
                "standard_relation": "=",
                "standard_value": 11.0,
                "standard_units": "nM",
            }
        ]
    }
]

PUBCHEM_ONCOLOGY_DATA = [
    {
        "cid": 71496458,
        "iupac_name": "Osimertinib Mesylate Salt",
        # Same active parent as ChEMBL3353410 with mesylate salt to test deduplication & salt stripping!
        "canonical_smiles": "COc1cc(N(C)CCN(C)C)c(NC(=O)C=C)cc1Nc1nccc(n1)c1cn(C)c2ccccc12.CS(=O)(=O)O",
        "bioassays": [
            {
                "target_id": "TGT_EGFR",
                "target_name": "Epidermal Growth Factor Receptor",
                "gene_symbol": "EGFR",
                "cell_line": "H1975",
                "assay_name": "PubChem AID 12345: EGFR T790M Screening",
                "assay_type": "FUNCTIONAL",
                "activity_type": "IC50",
                "relation": "=",
                "value": 0.0014,
                "unit": "uM",  # 0.0014 uM = 1.4 nM
            }
        ]
    },
    {
        "cid": 176870,
        "iupac_name": "Erlotinib",
        "canonical_smiles": "COCCOC1=C(C=C2C(=C1)C(=NC=N2)NC3=CC=CC(=C3)C#C)OCCOC",
        "bioassays": [
            {
                "target_id": "TGT_EGFR",
                "target_name": "Epidermal Growth Factor Receptor",
                "gene_symbol": "EGFR",
                "cell_line": "A549",
                "assay_name": "EGFR wild-type binding",
                "assay_type": "BINDING",
                "activity_type": "Ki",
                "relation": "=",
                "value": 2.1,
                "unit": "nM",
            }
        ]
    }
]

INHOUSE_ONCOLOGY_DATA = [
    {
        "internal_batch_id": "ONC-EXP-2026-001",
        "notebook_ref": "ELN-BK42-P10",
        "smiles": "COc1cc(N(C)CCN(C)C)c(NC(=O)C=C)cc1Nc1nccc(n1)c1cn(C)c2ccccc12",  # Osimertinib internal re-assay
        "target_id": "TGT_EGFR",
        "target_name": "EGFR C797S Triple Mutant",
        "gene_symbol": "EGFR",
        "cell_line": "PC-9/C797S",
        "assay_name": "In-House Kinase-Glo Luciferase Assay",
        "assay_type": "BINDING",
        "activity_type": "IC50",
        "relation": ">",
        "value": 1000.0,
        "unit": "nM",
    }
]


async def main():
    print("Initializing database...")
    await init_db()

    async with AsyncSessionLocal() as session:
        print("\n--- Ingesting ChEMBL Oncology Dataset ---")
        chembl_adapter = ChEMBLAdapter()
        rep1 = await run_ingestion_task(
            db=session,
            source_adapter=chembl_adapter,
            dataset_name="ChEMBL Approved Oncology Kinase Inhibitors",
            dataset_version="v34.0",
            raw_records_data=CHEMBL_ONCOLOGY_DATA,
        )
        print("ChEMBL Ingestion QC Report:", json.dumps(rep1, indent=2))

        print("\n--- Ingesting PubChem Oncology Dataset (Tests Deduplication & Salt Stripping) ---")
        pubchem_adapter = PubChemAdapter()
        rep2 = await run_ingestion_task(
            db=session,
            source_adapter=pubchem_adapter,
            dataset_name="PubChem Oncology BioAssays",
            dataset_version="2026.01",
            raw_records_data=PUBCHEM_ONCOLOGY_DATA,
        )
        print("PubChem Ingestion QC Report:", json.dumps(rep2, indent=2))

        print("\n--- Ingesting In-House Wet-Lab Experimental Feedback ---")
        inhouse_adapter = InHouseExperimentAdapter()
        rep3 = await run_ingestion_task(
            db=session,
            source_adapter=inhouse_adapter,
            dataset_name="In-House Wet-Lab Screening Run 1",
            dataset_version="exp-2026-q1",
            raw_records_data=INHOUSE_ONCOLOGY_DATA,
        )
        print("In-House Ingestion QC Report:", json.dumps(rep3, indent=2))

    print("\n[SUCCESS] Oncology seed datasets successfully populated.")


if __name__ == "__main__":
    asyncio.run(main())
