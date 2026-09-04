"""
Security Boundaries, Authentication, and Multi-Tenancy Context (Section 24 of architecture).
Provides server-to-server API Key authentication and tenant isolation context.
"""
from dataclasses import dataclass
from typing import Optional
from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials
from app.config.settings import settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
tenant_header = APIKeyHeader(name="X-Tenant-ID", auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class TenantContext:
    """Represents the authenticated tenant context for multi-tenant data isolation."""
    tenant_id: Optional[str]
    api_key: str
    is_admin: bool = False

    def __str__(self) -> str:
        return self.api_key


async def verify_api_key(
    header_key: Optional[str] = Security(api_key_header),
    header_tenant: Optional[str] = Security(tenant_header),
    bearer_creds: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
) -> TenantContext:
    """
    Validates API key provided in X-API-Key or Bearer token header.
    Resolves tenant context from X-Tenant-ID header.
    Returns authenticated TenantContext.
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

    tenant_id = header_tenant.strip() if header_tenant and header_tenant.strip() else None
    is_admin = (tenant_id in ("admin", "system")) or (tenant_id is None)

    return TenantContext(
        tenant_id=tenant_id,
        api_key=token,
        is_admin=is_admin,
    )
