# app/schemas/api_envelope.py
"""
V1 API contract envelope: shared response shape and error model.
Freeze-only: no architecture change; use for response_model so OpenAPI documents the contract.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

class ApiError(BaseModel):
    """V1 error payload inside ApiResponse.error."""
    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable message")
    details: Optional[Union[Dict[str, Any], List[Any], str]] = Field(
        default=None,
        description="Optional extra context (validation details, etc.)",
    )


class ApiResponse(BaseModel):
    """V1 success/error envelope. Use ApiResponse[Any] for OpenAPI when data shape varies."""
    ok: bool = Field(..., description="True if request succeeded")
    data: Optional[Any] = Field(default=None, description="Response payload when ok=True")
    error: Optional[ApiError] = Field(default=None, description="Error payload when ok=False")


# Type alias for endpoints that return arbitrary data (OpenAPI shows single envelope schema)
ApiResponseAny = ApiResponse


def ok_response(data: Any = None) -> ApiResponse:
    """Helper: build success envelope."""
    return ApiResponse(ok=True, data=data, error=None)


def err_response(code: str, message: str, details: Optional[Union[Dict[str, Any], List[Any], str]] = None) -> ApiResponse:
    """Helper: build error envelope."""
    return ApiResponse(ok=False, data=None, error=ApiError(code=code, message=message, details=details))
