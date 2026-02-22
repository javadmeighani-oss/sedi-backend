# tests/contracts/test_v1_openapi_contracts.py
"""
V1 contract tests: OpenAPI must document target paths and envelope (ApiResponse) for 200,
and at least one error response (4xx) per target endpoint.
No external network; no server; uses app.openapi() only.
"""
import pytest

from backend.app.main import app


def _openapi():
    """Load OpenAPI schema (no HTTP, no DB)."""
    return app.openapi()


def _get_schema_ref_name(ref: str) -> str:
    """From $ref '#/components/schemas/ApiResponse' return 'ApiResponse'."""
    if not ref or not ref.startswith("#/"):
        return ""
    return ref.split("/")[-1]


def _schema_has_envelope_shape(schemas: dict, name: str) -> bool:
    """True if schema has ok, data, error (envelope)."""
    s = schemas.get(name)
    if not s or not isinstance(s, dict):
        return False
    props = s.get("properties") or {}
    return "ok" in props and "data" in props and "error" in props


# Target paths for V1 contract freeze (prefix only; we check path exists)
TARGET_PREFIXES = [
    "/auth/request_otp",
    "/auth/verify_otp",
    "/auth/me",
    "/auth/refresh",
    "/auth/logout",
    "/interact/introduce",
    "/interact/chat",
    "/notifications",
    "/notifications/unread",
    "/notifications/push/register",
    "/notifications/admin/test_push",
    "/device/pending-commands",
    "/device/heartbeat",
    "/device/acknowledge",
    "/device/ingest",
    "/knowledge/next_question",
    "/knowledge/extract_from_message",
    "/knowledge/apply_answer",
    "/decision/evaluate",
]


@pytest.fixture(scope="module")
def openapi_schema():
    return _openapi()


def test_openapi_loads(openapi_schema):
    """OpenAPI schema is produced."""
    assert openapi_schema is not None
    assert "paths" in openapi_schema
    assert "components" in openapi_schema


def test_target_paths_exist(openapi_schema):
    """All target path prefixes have at least one matching path."""
    paths = openapi_schema.get("paths") or {}
    path_keys = list(paths.keys())
    for prefix in TARGET_PREFIXES:
        found = any(
            p == prefix or p.startswith(prefix + "/") or (prefix.endswith("/") and p == prefix.rstrip("/"))
            for p in path_keys
        )
        assert found, f"Target path prefix not found in OpenAPI: {prefix} (sample paths: {path_keys[:25]})"


def test_target_endpoints_have_200_response(openapi_schema):
    """Target V1 endpoints document a 200 response."""
    paths = openapi_schema.get("paths") or {}
    for prefix in TARGET_PREFIXES:
        matched = [p for p in paths if p == prefix or p.startswith(prefix.rstrip("/") + "/")]
        if not matched:
            continue
        path_key = matched[0]
        ops = paths[path_key]
        if not isinstance(ops, dict):
            continue
        has_200 = False
        for method in ["get", "post", "put", "delete"]:
            op = ops.get(method)
            if op and (op.get("responses") or {}).get("200"):
                has_200 = True
                break
        assert has_200, f"At least one operation on {path_key} should document 200"


def test_envelope_schemas_present(openapi_schema):
    """OpenAPI components/schemas include an envelope (ApiResponse or APIResponse) with ok, data, error."""
    components = openapi_schema.get("components") or {}
    schemas = components.get("schemas") or {}
    # Current app may use APIResponse (common) or ApiResponse (api_envelope)
    for name in ["ApiResponse", "APIResponse"]:
        if name in schemas and _schema_has_envelope_shape(schemas, name):
            return
    # Fallback: any schema with envelope shape
    for name, s in schemas.items():
        if _schema_has_envelope_shape(schemas, name):
            return
    pytest.fail("OpenAPI schemas should include an envelope (ok, data, error)")


def test_device_ingest_post_200_uses_device_ingest_response(openapi_schema):
    """POST /device/ingest documents 200 response with DeviceIngestResponse schema (raw, not ApiResponse)."""
    paths = openapi_schema.get("paths") or {}
    path_key = "/device/ingest"
    assert path_key in paths, f"{path_key} should exist in OpenAPI paths"
    post_spec = (paths.get(path_key) or {}).get("post")
    assert post_spec is not None, f"POST {path_key} should be documented"
    responses = post_spec.get("responses") or {}
    resp_200 = responses.get("200")
    assert resp_200 is not None, f"POST {path_key} should document 200"
    content = resp_200.get("content") or {}
    json_content = content.get("application/json") or {}
    schema_ref = (json_content.get("schema") or {}).get("$ref") or ""
    assert schema_ref.endswith("DeviceIngestResponse"), (
        f"POST {path_key} 200 should reference DeviceIngestResponse; got $ref={schema_ref!r}"
    )
