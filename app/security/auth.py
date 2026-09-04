"""
Security Boundaries and Authentication (Section 24 of architecture).
Provides server-to-server API Key authentication and tenant context.
"""
from typing import Optional
from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials
from app.config.settings import settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)


async def verify_api_key(
    header_key: Optional[str] = Security(api_key_header),
    bearer_creds: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
) -> str:
    """
    Validates API key provided in X-API-Key or Bearer token header.
    Returns authenticated key identifier.
    """
    token = None
    if header_key:
        token = header_key.strip()
    elif bearer_creds and bearer_creds.credentials:
        token = bearer_creds.credentials.strip()

    if not token or token != settings.API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return token
