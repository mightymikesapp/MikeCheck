import pytest
from fastapi.testclient import TestClient

from app.api import app

client = TestClient(app)


@pytest.mark.unit
def test_security_headers_present():
    response = client.get("/")
    assert response.status_code == 200
    headers = response.headers

    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


@pytest.mark.unit
def test_cors_rejects_evil_origin():
    # Test CORS headers with disallowed origin
    response = client.options(
        "/", headers={"Origin": "http://evil.com", "Access-Control-Request-Method": "GET"}
    )

    # Starlette/FastAPI CORS middleware returns 400 for disallowed origins if enforcing
    # or omits the header.
    if response.status_code == 200:
        assert response.headers.get("access-control-allow-origin") != "http://evil.com"
        assert response.headers.get("access-control-allow-origin") != "*"
    else:
        # If it's not 200, it's rejected, which is good.
        assert response.status_code == 400


@pytest.mark.unit
def test_cors_allows_localhost():
    # Test CORS headers with allowed origin
    origin = "http://localhost:8000"
    response = client.options(
        "/", headers={"Origin": origin, "Access-Control-Request-Method": "GET"}
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert response.headers["access-control-allow-credentials"] == "true"
