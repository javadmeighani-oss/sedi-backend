# Re-export from main backend.app.schemas.common for pytest compatibility
from backend.app.schemas.common import APIResponse, ErrorInfo

__all__ = ["APIResponse", "ErrorInfo"]
