import pytest
from fastapi import HTTPException, status
from starlette.requests import Request

from app import auth
from app.config import settings


@pytest.fixture(autouse=True)
def reset_api_key_manager() -> None:
    """Reset API key manager after each test to reload settings."""
    auth._api_key_manager = None
    yield
    auth._api_key_manager = None


def make_request(query: str | None = None, headers: dict[str, str] | None = None) -> Request:
    """Build a Starlette request for testing authentication flows."""
    scope: dict[str, object] = {
        "type": "http",
        "method": "GET",
        "path": "/protected",
        "scheme": "http",
        "server": ("testserver", 80),
        "headers": [(b"host", b"testserver")],
    }

    if query:
        scope["query_string"] = query.encode()

    if headers:
        scope["headers"].extend(
            (name.lower().encode(), value.encode()) for name, value in headers.items()
        )

    return Request(scope)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_verify_api_key_allows_query_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "enable_api_key_auth", True)
    monkeypatch.setattr(settings, "allow_api_key_query_param", True)
    monkeypatch.setattr(settings, "api_keys", "token123")

    request = make_request(query="api_key=token123")

    api_key = await auth.verify_api_key(request)

    assert api_key == "token123"


@pytest.mark.asyncio
async def test_verify_api_key_ignores_query_when_disabled(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(settings, "enable_api_key_auth", True)
    monkeypatch.setattr(settings, "allow_api_key_query_param", False)
    monkeypatch.setattr(settings, "api_keys", "token123")

    request = make_request(query="api_key=token123")

    with caplog.at_level("INFO"):
        with pytest.raises(HTTPException) as exc_info:
            await auth.verify_api_key(request)

    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert "query parameter ignored" in caplog.text.lower()
