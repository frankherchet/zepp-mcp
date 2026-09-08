from __future__ import annotations

import urllib.parse

import httpx
import pytest

from zepp_mcp.auth import (
    PasswordAuthProvider,
    StaticTokenAuthProvider,
    ZeppAuthError,
    ZeppAuthRejected,
)


@pytest.mark.asyncio
async def test_static_token_provider_returns_credentials() -> None:
    provider = StaticTokenAuthProvider(
        "app-token",
        "123",
        api_base_url="https://api-mifit-de2.zepp.com",
        country_code="DE",
    )
    credentials = await provider.authenticate()
    assert credentials.app_token == "app-token"
    assert credentials.user_id == "123"
    assert credentials.auth_flow == "token"


@pytest.mark.asyncio
async def test_password_provider_uses_modern_eu_flow() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host or "")
        if request.url.host == "api-user-de2.zepp.com":
            assert request.headers["x-hm-ekv"] == "1"
            assert request.url.path == "/v2/registrations/tokens"
            return httpx.Response(
                302,
                headers={
                    "Location": "https://example.invalid/success?access=access-code&country_code=DE"
                },
            )
        if request.url.host == "api-mifit-de2.zepp.com":
            form = urllib.parse.parse_qs(request.content.decode())
            assert form["code"] == ["access-code"]
            assert form["country_code"] == ["DE"]
            return httpx.Response(
                200,
                json={"token_info": {"app_token": "app-token", "user_id": 42}},
            )
        raise AssertionError(f"Unexpected auth request: {request.url}")

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = PasswordAuthProvider(
        "person@example.com",
        "test-value",
        country_code="DE",
        region="auto",
        http_client=http,
    )
    try:
        credentials = await provider.authenticate()
    finally:
        await http.aclose()

    assert calls == ["api-user-de2.zepp.com", "api-mifit-de2.zepp.com"]
    assert credentials.app_token == "app-token"
    assert credentials.user_id == "42"
    assert credentials.country_code == "DE"
    assert credentials.api_base_url == "https://api-mifit-de2.zepp.com"
    assert credentials.auth_flow == "zepp-v2-eu"


@pytest.mark.asyncio
async def test_password_provider_falls_back_to_legacy_flow() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host or "")
        if request.url.host == "api-user-de2.zepp.com":
            return httpx.Response(500)
        if request.url.host == "api-user.huami.com":
            assert request.url.path.endswith("person@example.com/tokens")
            assert b"person%40example.com/tokens" in request.url.raw_path
            return httpx.Response(200, json={"access": "legacy-access", "country_code": "DE"})
        if request.url.host == "account.huami.com":
            form = urllib.parse.parse_qs(request.content.decode())
            assert form["code"] == ["legacy-access"]
            return httpx.Response(
                200,
                json={"token_info": {"app_token": "legacy-token", "user_id": "77"}},
            )
        raise AssertionError(f"Unexpected auth request: {request.url}")

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = PasswordAuthProvider(
        "person@example.com",
        "test-value",
        country_code="DE",
        http_client=http,
    )
    try:
        credentials = await provider.authenticate()
    finally:
        await http.aclose()

    assert calls == ["api-user-de2.zepp.com", "api-user.huami.com", "account.huami.com"]
    assert credentials.app_token == "legacy-token"
    assert credentials.user_id == "77"
    assert credentials.auth_flow == "huami-legacy"


@pytest.mark.asyncio
async def test_explicit_rejection_does_not_retry_on_legacy_endpoint() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(401)

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = PasswordAuthProvider(
        "person@example.com",
        "test-value",
        country_code="DE",
        http_client=http,
    )
    try:
        with pytest.raises(ZeppAuthRejected, match="rejected"):
            await provider.authenticate()
    finally:
        await http.aclose()

    assert calls == 1


@pytest.mark.asyncio
async def test_auth_errors_do_not_echo_login_secret() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = PasswordAuthProvider(
        "person@example.com",
        "unique-test-value",
        country_code="DE",
        http_client=http,
    )
    try:
        with pytest.raises(ZeppAuthError) as captured:
            await provider.authenticate()
    finally:
        await http.aclose()

    assert "unique-test-value" not in str(captured.value)
