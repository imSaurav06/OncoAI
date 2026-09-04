# Canonical Data Model Specification

## 1. Domain Entities & Relationships

The platform defines a clean separation between **chemical structure identity**, **biological assays**, **activity measurements**, and **data provenance**.

```
┌─────────────────┐       1:N       ┌──────────────────────┐
│  SourceRecord   ├────────────────►│   CompoundIdentifier │
└────────┬────────┘                 └──────────┬───────────┘
         │                                     │ N:1
         │ maps to                             ▼
         │                          ┌──────────────────────┐
         └─────────────────────────►│       Compound       │
                                    └──────────┬───────────┘
                                               │ 1:1
                                               ▼
                                    ┌──────────────────────┐
                                    │  ChemicalStructure   │
                                    └──────────┬───────────┘
                                               │ 1:1
                                               ▼
                                    ┌──────────────────────┐
                                    │   MolecularFeature   │
                                    └──────────────────────┘

┌─────────────┐       1:N       ┌─────────────┐       1:N       ┌────────────────┐
│   Target    ├────────────────►│    Assay    ├────────────────►│  Bioactivity   │
└─────────────┘                 └──────┬──────┘                 └───────┬────────┘
                                       │                                │ N:1
┌─────────────┐       1:N              │                                │
│  CellLine   ├────────────────────────┘                                │
└─────────────┘                                                         ▼
                                                                ┌────────────────┐
                                                                │    Compound    │
                                                                └────────────────┘
```

---

## 2. Entity Definitions

### `Compound`
- `id` (UUID): Internal immutable primary identifier.
- `canonical_smiles` (VARCHAR): Standardized, salt-stripped, tautomer-canonicalized SMILES.
- `inchikey` (VARCHAR(27), Unique Index): 27-character standard InChIKey.
- `inchi` (TEXT): Full canonical IUPAC InChI string.
- `molecular_formula` (VARCHAR(128)): Stoichiometric formula (e.g., `C28H35N7O2`).
- `molecular_weight` (FLOAT): Average molecular mass ($g/\text{mol}$).
- `exact_mass` (FLOAT): Monoisotopic exact mass ($g/\text{mol}$).
- `heavy_atom_count` (INT): Total non-hydrogen atom count.
- `formal_charge` (INT): Net molecular charge after neutralization.
- `has_stereochemistry` (BOOLEAN): Flag indicating defined chiral centers.
- `standardization_version` (VARCHAR): Version of the standardization engine.
- `created_at`, `updated_at` (TIMESTAMP WITH TIME ZONE).

### `ChemicalStructure`
- `id` (UUID)
- `compound_id` (UUID, Foreign Key -> `Compound.id`)
- `original_smiles` (TEXT): Raw input SMILES prior to standardization.
- `standardized_smiles` (TEXT): Standardized SMILES representation.
- `mol_block` (TEXT): V2000/V3000 chemical table connection block.
- `murcko_scaffold` (TEXT): Bemis-Murcko core scaffold SMILES.

### `MolecularFeature`
- `id` (UUID)
- `compound_id` (UUID, Foreign Key -> `Compound.id`)
- `morgan_fp_r2_2048` (VARCHAR(512)): 2048-bit ECFP4 fingerprint serialized as a 512-character hexadecimal bitmask.
- `popcount` (INT, Indexed): Number of active bits for Fast Popcount filtering.
- `clogp` (FLOAT): Wildman-Crippen partition coefficient.
- `tpsa` (FLOAT): Topological polar surface area ($\text{Å}^2$).
- `hbd` (INT): Hydrogen bond donor count (Lipinski).
- `hba` (INT): Hydrogen bond acceptor count (Lipinski).
- `rotatable_bonds` (INT): Number of non-terminal flexible rotatable bonds.
- `aromatic_rings` (INT), `aliphatic_rings` (INT), `chiral_centers` (INT).

### `Target`
- `id` (UUID)
- `name` (VARCHAR): Target common name (e.g., `EGFR`, `BRAF V600E`).
- `uniprot_id` (VARCHAR): UniProt accession code (e.g., `P00533`).
- `target_type` (VARCHAR): e.g., `PROTEIN KINASE`, `NUCLEAR RECEPTOR`.
- `organism` (VARCHAR): e.g., `Homo sapiens`.

### `Assay`
- `id` (UUID)
- `target_id` (UUID, Foreign Key -> `Target.id`)
- `cell_line_id` (UUID, Foreign Key -> `CellLine.id`, Nullable)
- `assay_type` (VARCHAR): `BINDING`, `FUNCTIONAL`, `CELLULAR`, `PHENOTYPIC`.
- `description` (TEXT): Assay protocol description.
- `is_experimental` (BOOLEAN): `False` for public records, `True` for proprietary wet-lab observations.

### `Bioactivity`
- `id` (UUID)
- `compound_id` (UUID, Foreign Key -> `Compound.id`)
- `assay_id` (UUID, Foreign Key -> `Assay.id`)
- `activity_type` (VARCHAR, Indexed): `IC50`, `EC50`, `Ki`, `Kd`, `GI50`.
- `original_value` (FLOAT): Value as reported in the literature or laboratory notebook.
- `original_unit` (VARCHAR): e.g., `uM`, `nM`, `ug/mL`.
- `original_relation` (VARCHAR): `=`, `<`, `>`, `~`.
- `activity_value_nm` (FLOAT, Indexed): Standardized concentration normalized to canonical nanomolar ($\text{nM}$).
- `pactivity` (FLOAT, Indexed): Negative base-10 log of molar concentration ($-\log_{10}[\text{M}]$).
- `provenance_id` (UUID, Foreign Key -> `Provenance.id`).
