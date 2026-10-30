"""Pilot hardening of the public API surface (docs off, CORS allow-list, security headers)."""

from backend.app.core import api_surface


def test_docs_are_off_by_default_and_on_only_when_asked():
    off = api_surface.docs_urls({})
    assert off == {"docs_url": None, "redoc_url": None, "openapi_url": None}
    assert api_surface.docs_urls({"SEDI_EXPOSE_DOCS": "false"})["openapi_url"] is None
    on = api_surface.docs_urls({"SEDI_EXPOSE_DOCS": "True"})
    assert on == {"docs_url": "/docs", "redoc_url": "/redoc", "openapi_url": "/openapi.json"}


def test_cors_is_closed_by_default_and_never_a_wildcard():
    assert api_surface.cors_origins({}) == []
    assert api_surface.cors_origins({"CORS_ALLOW_ORIGINS": "  "}) == []
    assert api_surface.cors_origins({"CORS_ALLOW_ORIGINS": "*"}) == []
    got = api_surface.cors_origins({"CORS_ALLOW_ORIGINS": "https://a.example/, https://b.example ,*, https://a.example"})
    assert got == ["https://a.example", "https://b.example"]


def test_headers_and_hsts_only_over_https():
    plain = api_surface.security_headers(https=False)
    assert plain["X-Content-Type-Options"] == "nosniff"
    assert plain["X-Frame-Options"] == "DENY"
    assert "Strict-Transport-Security" not in plain
    secure = api_surface.security_headers(https=True)
    assert secure["Strict-Transport-Security"] == api_surface.HSTS_VALUE
    assert "includeSubDomains" not in secure["Strict-Transport-Security"]


def test_https_detection_follows_the_proxy_header():
    assert api_surface.request_is_https("http", "https") is True
    assert api_surface.request_is_https("http", "https, http") is True
    assert api_surface.request_is_https("http", None) is False
    assert api_surface.request_is_https("https", None) is True


def test_running_app_hides_docs_and_sends_the_headers(client):
    # the test app is built without SEDI_EXPOSE_DOCS: documentation routes do not exist
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404, path
    r = client.get("/healthz", headers={"X-Forwarded-Proto": "https"})
    assert r.status_code == 200
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["strict-transport-security"] == api_surface.HSTS_VALUE
    assert "strict-transport-security" not in client.get("/healthz").headers


def test_a_foreign_browser_origin_gets_no_cors_permission(client):
    r = client.options(
        "/auth/me",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in r.headers


def test_openapi_schema_is_still_available_to_the_contract_tests():
    from backend.app.main import app

    assert app.openapi()["paths"]
