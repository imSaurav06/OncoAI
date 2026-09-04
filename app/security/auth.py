"""
Security Boundaries, Authentication, and Multi-Tenancy Context.
Provides real credential-derived tenant authentication and strict isolation boundaries.
"""
from dataclasses import dataclass
from typing import Dict, Optional
import re
from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials
from app.config.settings import settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
tenant_header = APIKeyHeader(name="X-Tenant-ID", auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class ApiKeyRecord:
    """Represents a registered API key entry with bound tenant identity."""
    api_key: str
    tenant_id: Optional[str]
    name: str = ""
    is_admin: bool = False
    is_active: bool = True


# In-memory tenant API key registry (can be seeded or backed by DB/vault)
_KEY_REGISTRY: Dict[str, ApiKeyRecord] = {}


def register_tenant_api_key(
    api_key: str,
    tenant_id: str,
    name: str = "",
    is_admin: bool = False,
) -> ApiKeyRecord:
    """Registers an API key bound to a specific tenant."""
    record = ApiKeyRecord(
        api_key=api_key,
        tenant_id=tenant_id,
        name=name,
        is_admin=is_admin,
        is_active=True,
    )
    _KEY_REGISTRY[api_key] = record
    return record


def clear_key_registry() -> None:
    """Clears the dynamic key registry (used in tests)."""
    _KEY_REGISTRY.clear()


@dataclass
class TenantContext:
    """
    Represents the authenticated tenant context for multi-tenant data isolation.
    Tenant identity is strictly derived from the authenticated credential.
    """
    tenant_id: Optional[str]
    api_key: str
    is_admin: bool = False

    def __str__(self) -> str:
        return f"TenantContext(tenant={self.tenant_id}, admin={self.is_admin})"


# Regex for structured tenant keys: onco_sk_<tenant_id>_<secret>
STRUCTURED_KEY_PATTERN = re.compile(r"^onco_sk_([a-zA-Z0-9_\-]+)_([a-zA-Z0-9]+)$")


async def verify_api_key(
    header_key: Optional[str] = Security(api_key_header),
    header_tenant: Optional[str] = Security(tenant_header),
    bearer_creds: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
) -> TenantContext:
    """
    Validates API credentials and derives tenant context.
    
    Security Rules:
    1. Master Admin Key (settings.API_KEY):
       - Granted is_admin = True.
       - Can inspect global data (tenant_id = None) or specify X-Tenant-ID to act on behalf of a tenant.
    2. Tenant Key (registered or structured 'onco_sk_<tenant>_<token>'):
       - Tenant identity is derived directly from the credential.
       - is_admin is strictly False.
       - If client supplies an X-Tenant-ID that does NOT match the credential's tenant,
         a 403 Forbidden is raised immediately (preventing header spoofing).
    3. Absence of tenant_id for non-admin keys is never allowed.
    4. Invalid credentials raise 401 Unauthorized.
    """
    token = None
    if isinstance(header_key, str) and header_key.strip():
        token = header_key.strip()
    elif isinstance(bearer_creds, HTTPAuthorizationCredentials) and bearer_creds.credentials:
        token = bearer_creds.credentials.strip()

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    clean_header_tenant = (
        header_tenant.strip()
        if isinstance(header_tenant, str) and header_tenant.strip()
        else None
    )

    # Case 1: Master Admin Key
    if token == settings.API_KEY:
        return TenantContext(
            tenant_id=clean_header_tenant,  # Admin can optionally specify tenant scope or operate globally
            api_key=token,
            is_admin=True,
        )

    # Case 2: Registered Key in Key Registry
    if token in _KEY_REGISTRY:
        record = _KEY_REGISTRY[token]
        if not record.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key has been revoked or deactivated",
            )
        
        # If admin key registered
        if record.is_admin:
            return TenantContext(
                tenant_id=clean_header_tenant or record.tenant_id,
                api_key=token,
                is_admin=True,
            )

        # Non-admin tenant key: verify header matches credential
        if clean_header_tenant and clean_header_tenant != record.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: X-Tenant-ID header '{clean_header_tenant}' does not match authenticated credential identity '{record.tenant_id}'",
            )

        return TenantContext(
            tenant_id=record.tenant_id,
            api_key=token,
            is_admin=False,
        )

    # Case 3: Structured Tenant Key (onco_sk_<tenant_id>_<secret>)
    match = STRUCTURED_KEY_PATTERN.match(token)
    if match:
        credential_tenant = match.group(1)
        # Verify header does not spoof different tenant
        if clean_header_tenant and clean_header_tenant != credential_tenant:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: X-Tenant-ID header '{clean_header_tenant}' does not match authenticated credential identity '{credential_tenant}'",
            )
        return TenantContext(
            tenant_id=credential_tenant,
            api_key=token,
            is_admin=False,
        )

    # Unrecognized token
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API authentication credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
