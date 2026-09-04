"""
API Middleware for Request Tracing, Latency Measurement, and Consistent Error Envelopes.
"""
import time
import uuid
from datetime import datetime, timezone
from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.schemas.envelope import ApiResponse, ResponseMeta, ErrorDetail
from app.chemistry.pipeline import ChemistryPipelineError
import rdkit


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
        request.state.request_id = request_id
        start_time = time.perf_counter()

        response: Response = await call_next(request)

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time-Ms"] = str(duration_ms)
        return response


def create_error_response(
    request_id: str,
    status_code: int,
    error_code: str,
    message: str,
    field: str = None
) -> JSONResponse:
    """Constructs a standard machine-readable API error response envelope."""
    envelope = ApiResponse(
        schema_version="1.0",
        api_version="v1",
        request_id=request_id,
        status="error",
        data=None,
        meta=ResponseMeta(
            rdkit_version=rdkit.__version__,
            pipeline_version="chem-std-1.0.0",
            timestamp=datetime.now(timezone.utc).isoformat(),
        ),
        errors=[ErrorDetail(code=error_code, message=message, field=field)],
    )
    return JSONResponse(status_code=status_code, content=envelope.model_dump())
