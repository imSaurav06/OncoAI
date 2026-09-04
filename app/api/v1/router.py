"""
Versioned API Router (v1).
"""
from fastapi import APIRouter
from app.api.v1.compounds import router as compounds_router
from app.api.v1.bioactivity import router as bioactivity_router
from app.api.v1.sources import router as sources_router
from app.api.v1.jobs import router as jobs_router

api_v1_router = APIRouter()

api_v1_router.include_router(compounds_router)
api_v1_router.include_router(bioactivity_router)
api_v1_router.include_router(sources_router)
api_v1_router.include_router(jobs_router)
