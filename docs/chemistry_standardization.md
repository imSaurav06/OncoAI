# Chemistry Standardization Specification (RDKit 2024.03.5)

## 1. Objective & Philosophy
Chemical structures ingested from external databases (ChEMBL, PubChem, patents, research literature) frequently contain salts, counterions, solvent adducts, stereochemical ambiguity, non-standard tautomeric forms, and arbitrary charge states.

The OncoAI Chemistry Standardization Pipeline enforces a **deterministic, 9-stage transformation protocol** implemented in Python utilizing pinned `RDKit 2024.03.5`.

---

## 2. 9-Stage Standardization Pipeline

```
Raw Structure (SMILES / SDF)
  │
  ├─► Stage 1: SMILES Parsing (`Chem.MolFromSmiles`)
  │      └─ Handles valence and parse errors; rejects malformed inputs
  │
  ├─► Stage 2: Structural Validation (`validators.validate_molecule`)
  │      └─ Rejects empty molecules, zero-heavy-atom ions, non-organic atoms
  │
  ├─► Stage 3: Disconnect Organometallics (`rdMolStandardize.MetalDisconnector`)
  │      └─ Breaks ionic coordinate bonds to transition metals and alkali ions
  │
  ├─► Stage 4: Salt Stripping & Component Selection (`rdMolStandardize.FragmentParent`)
  │      └─ Extracts largest organic covalently connected component
  │      └─ Discards counterions (TFA, HCl, Acetate, Tartrate, etc.)
  │
  ├─► Stage 5: Charge Normalization (`rdMolStandardize.Normalizer`)
  │      └─ Corrects hypervalent nitro groups, sulfoxides, azides
  │
  ├─► Stage 6: Uncharging / Neutralization (`rdMolStandardize.Uncharger`)
  │      └─ Neutralizes zwitterions and protonated amines where chemically feasible
  │
  ├─► Stage 7: Canonical Tautomer Enumeration (`rdMolStandardize.CanonicalTautomer`)
  │      └─ Selects single deterministic resonance/tautomer representation (e.g. keto-enol)
  │
  ├─► Stage 8: Canonical Identifier Generation
  │      └─ Generates Canonical SMILES, standard InChI, and standard InChIKey (27-char)
  │
  └─► Stage 9: Descriptors & ECFP4 Fingerprint Generation
         └─ 2048-bit Morgan Fingerprint (radius=2) via `rdFingerprintGenerator`
         └─ Monoisotopic Exact Mass, MW, CLogP, TPSA, HBD, HBA, Rotatable Bonds
```

---

## 3. Explicit Handling of Edge Cases

### Salts and Solvates
Multi-component SMILES (e.g., `Osimertinib.mesylate`: `... .CS(=O)(=O)O`) are systematically stripped using `rdMolStandardize.FragmentParent(mol)`. The parent free base is retained for canonical identity, while the original salt representation is preserved in `ChemicalStructure.original_smiles`.

### Tautomers
Keto-enol and amidine-amidrazone equilibrium states are collapsed to a single canonical tautomer via RDKit's scoring rules. This ensures that two distinct publications drawing two tautomers of the same drug resolve to the identical canonical compound.

### Problematic Records & Rejection Logging
If a record fails at any stage (e.g., nitrogen with valence 5 not matching known nitro/oxide patterns), it is **never silently dropped**. Instead, an explicit record is written to the `RejectedRecord` table and QC telemetry logs detailing:
- `source_record_id`
- `rejection_reason` (e.g., `Explicit valence for atom # 3 N, 5, is greater than permitted`)
- `processing_version`
- `timestamp`
