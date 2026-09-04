"""
Main FastAPI Application Entrypoint.
OncoAI Chemistry & Bioactivity Data Platform — Production Foundation v1.
"""
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import rdkit

from app.config.settings import settings
from app.storage.database import init_db, AsyncSessionLocal
from app.api.middleware import RequestContextMiddleware
from app.api.v1.router import api_v1_router
from app.indexing.query_planner import query_planner

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("oncoai")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: verify RDKit version and initialize database tables
    logger.info(f"Starting {settings.APP_NAME}...")
    logger.info(f"RDKit Version: {rdkit.__version__} (Configured: {settings.EXPECTED_RDKIT_VERSION})")
    
    await init_db()
    logger.info("Relational database tables initialized.")

    # Preload similarity index in background
    async with AsyncSessionLocal() as session:
        await query_planner.ensure_similarity_index_populated(session)
    logger.info("Molecular similarity index warmed up.")

    yield
    logger.info("Shutting down OncoAI Data Platform.")


app = FastAPI(
    title=settings.APP_NAME,
    description="""
# OncoAI Chemistry & Bioactivity Data Platform (v1)

A scalable, API-first scientific data backbone for oncology drug discovery.

### Capabilities:
* **Deterministic RDKit Standardization**: Multi-stage parsing, salt stripping, charge neutralization, and tautomer canonicalization.
* **Bioactivity & Unit Normalization**: Heterogeneous activity types (IC50, Ki, EC50) normalized to canonical nM with pActivity.
* **Entity Deduplication**: InChIKey-based multi-source resolution collapsing duplicates while retaining full provenance.
* **High-Performance Molecular Similarity**: Popcount-bounded Morgan (ECFP4) bitwise Tanimoto screening.
* **Tiered Data Lake**: Cold S3-compatible raw lake, Warm columnar Parquet lake, and Hot PostgreSQL serving store.
* **Asynchronous Jobs**: Non-blocking background worker for batch ingestion and processing.
* **Scientific Lineage & QC**: Full audit trail and data quality reports for every observation.
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# Middleware
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Versioned API
app.include_router(api_v1_router, prefix=settings.API_V1_STR)


@app.get("/health", tags=["Observability"], summary="Liveness check")
async def health_check():
    """Liveness probe reporting platform and RDKit operational status."""
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "rdkit_version": rdkit.__version__,
        "pipeline_version": settings.PIPELINE_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/ready", tags=["Observability"], summary="Readiness check")
async def readiness_check():
    """Readiness probe verifying database connectivity."""
    try:
        from sqlalchemy import text
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return {
            "status": "ready",
            "database": "connected",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "not_ready", "error": str(exc)},
        )


@app.get("/metrics", tags=["Observability"], summary="Platform telemetry metrics")
async def metrics():
    """Returns runtime pipeline metrics and index size."""
    from app.indexing.similarity import similarity_index
    return {
        "similarity_index_cached_molecules": similarity_index.size(),
        "rdkit_version": rdkit.__version__,
        "pipeline_version": settings.PIPELINE_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
