"""
Decoupled Query Planner (Sections 14 & 38 of architecture).
Translates SaaS search requests into candidate retrieval, structured filtering, ranking, and response assembly.
"""
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy import select, and_, or_, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from rdkit import Chem

from app.models.compound import Compound, MolecularFeature, CompoundIdentifier
from app.models.bioactivity import Bioactivity, Target, CellLine, Assay
from app.models.source import Source, SourceRecord
from app.indexing.similarity import similarity_index
from app.chemistry.fingerprints import hex_to_fingerprint
from app.chemistry.pipeline import chemistry_pipeline


class QueryPlanner:
    """
    Coordinates multi-tier retrieval:
    1. Candidate screening (exact, similarity index, or property bounds)
    2. Structured filtering (relational attributes, bioactivities)
    3. Top-K ranking and enrichment
    """

    async def ensure_similarity_index_populated(self, db: AsyncSession) -> None:
        """Hydrates the in-memory similarity index from the database if empty."""
        if similarity_index.size() == 0:
            stmt = select(MolecularFeature.compound_id, MolecularFeature.morgan_fp_2048_hex)
            res = await db.execute(stmt)
            records = res.all()
            if records:
                similarity_index.bulk_index([(r[0], r[1]) for r in records])

    async def search_compounds(
        self,
        db: AsyncSession,
        exact_inchikey: Optional[str] = None,
        substructure_smiles: Optional[str] = None,
        min_mw: Optional[float] = None,
        max_mw: Optional[float] = None,
        min_clogp: Optional[float] = None,
        max_clogp: Optional[float] = None,
        min_tpsa: Optional[float] = None,
        max_tpsa: Optional[float] = None,
        scaffold_smiles: Optional[str] = None,
        molecular_formula: Optional[str] = None,
        identifier: Optional[str] = None,
        tenant_id: Optional[str] = None,
        is_admin: bool = False,
        limit: int = 50,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Executes multifaceted structured search across compound attributes with tenant isolation.
        """
        query = select(Compound).join(Compound.features).join(Compound.structure)

        conditions = []
        
        # Multi-tenant isolation: non-admin tenants can only see shared public data (tenant_id IS NULL)
        # or their own proprietary compounds (tenant_id == current_tenant)
        if not is_admin:
            if tenant_id:
                conditions.append(or_(Compound.tenant_id.is_(None), Compound.tenant_id == tenant_id))
            else:
                conditions.append(Compound.tenant_id.is_(None))

        if exact_inchikey:
            conditions.append(Compound.inchikey == exact_inchikey.strip())
        if min_mw is not None:
            conditions.append(Compound.molecular_weight >= min_mw)
        if max_mw is not None:
            conditions.append(Compound.molecular_weight <= max_mw)
        if min_clogp is not None:
            conditions.append(MolecularFeature.clogp >= min_clogp)
        if max_clogp is not None:
            conditions.append(MolecularFeature.clogp <= max_clogp)
        if min_tpsa is not None:
            conditions.append(MolecularFeature.tpsa >= min_tpsa)
        if max_tpsa is not None:
            conditions.append(MolecularFeature.tpsa <= max_tpsa)
        if scaffold_smiles:
            conditions.append(Compound.murcko_scaffold_smiles == scaffold_smiles.strip())
        if molecular_formula:
            conditions.append(Compound.molecular_formula == molecular_formula.strip())

        if identifier:
            # Join with identifiers
            query = query.join(Compound.identifiers)
            conditions.append(CompoundIdentifier.identifier_value.ilike(f"%{identifier.strip()}%"))

        if conditions:
            query = query.where(and_(*conditions))

        # Count total matching
        subq = query.subquery()
        count_stmt = select(func.count()).select_from(subq)
        count_res = await db.execute(count_stmt)
        total_count = count_res.scalar_one() or 0

        # Substructure search post-filter if requested
        if substructure_smiles:
            pattern = Chem.MolFromSmarts(substructure_smiles) or Chem.MolFromSmiles(substructure_smiles)
            if pattern is None:
                raise ValueError(f"Invalid substructure query SMILES/SMARTS: {substructure_smiles}")

            # Fetch candidates for substructure evaluation
            res = await db.execute(query.options(selectinload(Compound.features)))
            compounds = res.scalars().all()
            matched = []
            for c in compounds:
                mol = Chem.MolFromSmiles(c.canonical_smiles)
                if mol and mol.HasSubstructMatch(pattern):
                    matched.append(c)

            total_count = len(matched)
            paginated = matched[offset : offset + limit]
            return [self._compound_to_dict(c) for c in paginated], total_count

        # Normal pagination
        query = query.offset(offset).limit(limit).options(selectinload(Compound.features))
        res = await db.execute(query)
        compounds = res.scalars().all()

        return [self._compound_to_dict(c) for c in compounds], total_count

    async def search_similarity(
        self,
        db: AsyncSession,
        query_smiles: str,
        threshold: float = 0.8,
        limit: int = 50,
        target_id: Optional[str] = None,
        activity_type: Optional[str] = None,
        max_activity_nm: Optional[float] = None,
        tenant_id: Optional[str] = None,
        is_admin: bool = False,
    ) -> Dict[str, Any]:
        """
        Executes similarity search with optional joint bioactivity constraints and tenant isolation.
        """
        await self.ensure_similarity_index_populated(db)

        # Standardize query molecule to generate canonical query fingerprint
        analysis = chemistry_pipeline.analyze(query_smiles)
        query_fp = hex_to_fingerprint(analysis.fingerprint_hex)

        candidate_ids = None

        # Multi-tenant compound boundary
        if not is_admin:
            if tenant_id:
                t_stmt = select(Compound.compound_id).where(
                    or_(Compound.tenant_id.is_(None), Compound.tenant_id == tenant_id)
                )
            else:
                t_stmt = select(Compound.compound_id).where(Compound.tenant_id.is_(None))
            allowed_cids = set((await db.execute(t_stmt)).scalars().all())
            candidate_ids = allowed_cids

        # If bioactivity constraints are provided, find matching compound_ids first
        if target_id or activity_type or max_activity_nm is not None:
            bio_query = select(Bioactivity.compound_id).join(Bioactivity.assay)
            bio_conds = []
            if not is_admin:
                if tenant_id:
                    bio_conds.append(or_(Bioactivity.tenant_id.is_(None), Bioactivity.tenant_id == tenant_id))
                else:
                    bio_conds.append(Bioactivity.tenant_id.is_(None))
            if target_id:
                bio_conds.append(Assay.target_id == target_id)
            if activity_type:
                bio_conds.append(Bioactivity.activity_type == activity_type)
            if max_activity_nm is not None:
                bio_conds.append(Bioactivity.normalized_value <= max_activity_nm)

            bio_query = bio_query.where(and_(*bio_conds))
            res = await db.execute(bio_query)
            bio_cids = set(res.scalars().all())

            if candidate_ids is None:
                candidate_ids = bio_cids
            else:
                candidate_ids = candidate_ids.intersection(bio_cids)

            if not candidate_ids:
                return {
                    "query_smiles": query_smiles,
                    "query_canonical_smiles": analysis.standardization.canonical_smiles,
                    "query_inchikey": analysis.standardization.inchikey,
                    "threshold": threshold,
                    "limit": limit,
                    "total_matches": 0,
                    "items": [],
                }

        # Query fast similarity index
        similar_pairs = similarity_index.search_similar(
            query_fp=query_fp,
            threshold=threshold,
            limit=limit,
            candidate_ids=candidate_ids,
        )

        if not similar_pairs:
            return {
                "query_smiles": query_smiles,
                "query_canonical_smiles": analysis.standardization.canonical_smiles,
                "query_inchikey": analysis.standardization.inchikey,
                "threshold": threshold,
                "limit": limit,
                "total_matches": 0,
                "items": [],
            }

        # Hydrate compound metadata for matched IDs
        matched_ids = [cid for cid, _ in similar_pairs]
        c_stmt = (
            select(Compound)
            .where(Compound.compound_id.in_(matched_ids))
            .options(selectinload(Compound.features))
        )
        c_res = await db.execute(c_stmt)
        c_map = {c.compound_id: c for c in c_res.scalars().all()}

        items = []
        for cid, score in similar_pairs:
            comp = c_map.get(cid)
            if comp:
                c_dict = self._compound_to_dict(comp)
                c_dict["similarity_score"] = score
                items.append(c_dict)

        return {
            "query_smiles": query_smiles,
            "query_canonical_smiles": analysis.standardization.canonical_smiles,
            "query_inchikey": analysis.standardization.inchikey,
            "threshold": threshold,
            "limit": limit,
            "total_matches": len(items),
            "items": items,
        }

    async def search_bioactivity(
        self,
        db: AsyncSession,
        compound_id: Optional[str] = None,
        target_id: Optional[str] = None,
        gene_symbol: Optional[str] = None,
        cell_line: Optional[str] = None,
        activity_type: Optional[str] = None,
        min_normalized_value: Optional[float] = None,
        max_normalized_value: Optional[float] = None,
        min_p_activity: Optional[float] = None,
        is_censored: Optional[bool] = None,
        is_experimental: Optional[bool] = None,
        source_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        is_admin: bool = False,
        limit: int = 50,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Executes faceted bioactivity search across targets, cell lines, and activity types with tenant isolation.
        """
        query = (
            select(Bioactivity)
            .join(Bioactivity.assay)
            .outerjoin(Assay.target)
            .outerjoin(Assay.cell_line)
            .outerjoin(Bioactivity.source_record)
            .options(
                selectinload(Bioactivity.assay).selectinload(Assay.target),
                selectinload(Bioactivity.assay).selectinload(Assay.cell_line),
                selectinload(Bioactivity.compound),
                selectinload(Bioactivity.source_record),
            )
        )

        conditions = []
        
        # Multi-tenant isolation: non-admin tenants see shared public data or their own records
        if not is_admin:
            if tenant_id:
                conditions.append(or_(Bioactivity.tenant_id.is_(None), Bioactivity.tenant_id == tenant_id))
            else:
                conditions.append(Bioactivity.tenant_id.is_(None))

        if compound_id:
            conditions.append(Bioactivity.compound_id == compound_id.strip())
        if target_id:
            conditions.append(Assay.target_id == target_id.strip())
        if gene_symbol:
            conditions.append(Target.gene_symbol.ilike(gene_symbol.strip()))
        if cell_line:
            conditions.append(CellLine.name.ilike(cell_line.strip()))
        if activity_type:
            conditions.append(Bioactivity.activity_type == activity_type.strip())
        if min_normalized_value is not None:
            conditions.append(Bioactivity.normalized_value >= min_normalized_value)
        if max_normalized_value is not None:
            conditions.append(Bioactivity.normalized_value <= max_normalized_value)
        if min_p_activity is not None:
            conditions.append(Bioactivity.p_activity >= min_p_activity)
        if is_censored is not None:
            conditions.append(Bioactivity.is_censored == is_censored)
        if is_experimental is not None:
            conditions.append(Bioactivity.is_experimental == is_experimental)
        if source_id:
            conditions.append(SourceRecord.source_id == source_id.strip())

        if conditions:
            query = query.where(and_(*conditions))

        # Count total
        subq = query.subquery()
        count_stmt = select(func.count()).select_from(subq)
        count_res = await db.execute(count_stmt)
        total_count = count_res.scalar_one() or 0

        # Apply ordering and pagination
        query = query.order_by(Bioactivity.normalized_value.asc()).offset(offset).limit(limit)
        res = await db.execute(query)
        records = res.scalars().all()

        items = []
        for b in records:
            items.append({
                "bioactivity_id": b.bioactivity_id,
                "compound_id": b.compound_id,
                "canonical_smiles": b.compound.canonical_smiles if b.compound else None,
                "target_id": b.assay.target_id if b.assay else None,
                "target_name": b.assay.target.target_name if b.assay and b.assay.target else None,
                "gene_symbol": b.assay.target.gene_symbol if b.assay and b.assay.target else None,
                "cell_line": b.assay.cell_line.name if b.assay and b.assay.cell_line else None,
                "assay_type": b.assay.assay_type if b.assay else None,
                "activity_type": b.activity_type,
                "original_relation": b.original_relation,
                "original_value": b.original_value,
                "original_unit": b.original_unit,
                "normalized_relation": b.normalized_relation,
                "normalized_value": b.normalized_value,
                "normalized_unit": b.normalized_unit,
                "p_activity": b.p_activity,
                "p_activity_relation": b.p_activity_relation,
                "is_censored": b.is_censored,
                "is_experimental": b.is_experimental,
                "source_name": b.source_record.source_id if b.source_record else None,
                "external_id": b.source_record.external_id if b.source_record else None,
                "provenance_id": b.provenance_id,
            })

        return items, total_count

    def _compound_to_dict(self, comp: Compound) -> Dict[str, Any]:
        return {
            "compound_id": comp.compound_id,
            "canonical_smiles": comp.canonical_smiles,
            "inchikey": comp.inchikey,
            "molecular_formula": comp.molecular_formula,
            "molecular_weight": comp.molecular_weight,
            "has_stereochemistry": comp.has_stereochemistry,
            "clogp": comp.features.clogp if comp.features else 0.0,
            "tpsa": comp.features.tpsa if comp.features else 0.0,
            "heavy_atom_count": comp.heavy_atom_count,
            "formal_charge": comp.formal_charge,
            "murcko_scaffold_smiles": comp.murcko_scaffold_smiles,
        }


query_planner = QueryPlanner()
