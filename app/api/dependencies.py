"""
FastAPI Dependencies for Authentication, Database Sessions, and Request Context.
"""
from fastapi import Request
from app.storage.database import get_db
from app.security.auth import verify_api_key


def get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "req_unknown")
