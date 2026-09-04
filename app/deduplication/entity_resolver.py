"""
Entity Resolution and Compound Deduplication Engine (Section 8 of architecture).
Deterministically maps heterogeneous source records to unique canonical compounds via InChIKey.
"""
from typing import Optional, List, Tuple, Dict, Any
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.compound import Compound, ChemicalStructure, MolecularFeature, CompoundIdentifier
from app.models.source import SourceRecord
from app.chemistry.pipeline import chemistry_pipeline, AnalysisResult


class EntityResolver:
    """
    Handles resolution between raw source records and canonical chemical entities.
    Ensures that identical molecules from multiple sources collapse to one canonical Compound,
    while retaining complete source lineage.
    """

    @staticmethod
    def generate_compound_id() -> str:
        """Generates a prefixed unique internal compound identifier."""
        return f"CMP_{uuid.uuid4().hex[:12].upper()}"

    async def resolve_or_create_compound(
        self,
        db: AsyncSession,
        raw_smiles: str,
        identifiers: Optional[List[Dict[str, str]]] = None,
        source_record_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> Tuple[Compound, bool, AnalysisResult]:
        """
        Resolves an input SMILES to a canonical Compound.
        Returns: (Compound, is_newly_created, AnalysisResult)
        """
        # Step 1: Deterministic chemical analysis
        analysis = chemistry_pipeline.analyze(raw_smiles)
        std = analysis.standardization
        target_inchikey = std.inchikey

        # Step 2: Query existing compound by InChIKey (O(1) B-tree lookup)
        stmt = select(Compound).where(Compound.inchikey == target_inchikey)
        result = await db.execute(stmt)
        existing_compound = result.scalar_one_or_none()

        if existing_compound:
            # Compound already cataloged: update identifiers if new ones supplied
            if identifiers:
                await self._attach_identifiers(db, existing_compound.compound_id, identifiers, tenant_id=tenant_id)
            
            # If source record is provided, link it
            if source_record_id:
                src_stmt = select(SourceRecord).where(SourceRecord.source_record_id == source_record_id)
                src_res = await db.execute(src_stmt)
                src_record = src_res.scalar_one_or_none()
                if src_record:
                    src_record.compound_id = existing_compound.compound_id
                    src_record.status = "PROCESSED"

            return existing_compound, False, analysis

        # Step 3: Compound is novel -> create canonical entity
        compound_id = self.generate_compound_id()
        desc = analysis.descriptors

        new_compound = Compound(
            compound_id=compound_id,
            canonical_smiles=std.canonical_smiles,
            isomeric_smiles=std.isomeric_smiles,
            inchikey=std.inchikey,
            inchi=std.inchi,
            molecular_formula=desc["molecular_formula"],
            molecular_weight=desc["molecular_weight"],
            exact_mass=desc["exact_mass"],
            heavy_atom_count=desc["heavy_atom_count"],
            formal_charge=desc["formal_charge"],
            murcko_scaffold_smiles=analysis.murcko_scaffold,
            has_stereochemistry=std.has_stereochemistry,
            tenant_id=tenant_id,
            processing_version=analysis.pipeline_version,
            rdkit_version=analysis.rdkit_version,
        )
        db.add(new_compound)

        # Extended structure metadata
        new_structure = ChemicalStructure(
            compound_id=compound_id,
            num_rings=desc["num_rings"],
            num_aromatic_rings=desc["num_aromatic_rings"],
            num_aliphatic_rings=desc["num_aliphatic_rings"],
            num_chiral_centers=desc["num_chiral_centers"],
            num_defined_chiral_centers=desc["num_defined_chiral_centers"],
            num_undefined_chiral_centers=desc["num_undefined_chiral_centers"],
            is_salt=std.salt_removed,
            salt_fragment_smiles=std.salt_fragment_smiles,
            parent_compound_smiles=std.parent_smiles,
        )
        db.add(new_structure)

        # Precomputed molecular features & Morgan fingerprint
        new_features = MolecularFeature(
            compound_id=compound_id,
            clogp=desc["clogp"],
            tpsa=desc["tpsa"],
            hbd=desc["hbd"],
            hba=desc["hba"],
            rotatable_bonds=desc["rotatable_bonds"],
            fraction_csp3=desc["fraction_csp3"],
            morgan_fp_2048_hex=analysis.fingerprint_hex,
            fingerprint_version="morgan-r2-2048-v1",
        )
        db.add(new_features)

        # Attach any identifiers (IUPAC, trade name, external accession)
        if identifiers:
            await self._attach_identifiers(db, compound_id, identifiers, tenant_id=tenant_id)

        # Link source record if provided
        if source_record_id:
            src_stmt = select(SourceRecord).where(SourceRecord.source_record_id == source_record_id)
            src_res = await db.execute(src_stmt)
            src_record = src_res.scalar_one_or_none()
            if src_record:
                src_record.compound_id = compound_id
                src_record.status = "PROCESSED"

        await db.flush()
        return new_compound, True, analysis

    async def _attach_identifiers(
        self, db: AsyncSession, compound_id: str, identifiers: List[Dict[str, str]], tenant_id: Optional[str] = None
    ) -> None:
        """Appends new synonyms or identifiers to compound, avoiding duplicates."""
        stmt = select(CompoundIdentifier).where(CompoundIdentifier.compound_id == compound_id)
        res = await db.execute(stmt)
        existing = {(i.identifier_type, i.identifier_value) for i in res.scalars().all()}

        for item in identifiers:
            key = (item["identifier_type"], item["identifier_value"])
            if key not in existing:
                cid = CompoundIdentifier(
                    compound_id=compound_id,
                    source_id=item.get("source_id"),
                    tenant_id=tenant_id,
                    identifier_type=item["identifier_type"],
                    identifier_value=item["identifier_value"],
                )
                db.add(cid)
                existing.add(key)


entity_resolver = EntityResolver()
