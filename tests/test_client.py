from __future__ import annotations

import json

import httpx
import pytest

from zepp_mcp.client import ZeppApiError, ZeppClient
from zepp_mcp.config import Settings, make_settings


@pytest.fixture
def settings() -> Settings:
    return make_settings(
        {
            "ZEPP_APP_TOKEN": "test-token",
            "ZEPP_USER_ID": "42",
            "ZEPP_BASE_URL": "https://api.example.test",
        }
    )


@pytest.mark.asyncio
async def test_check_connection_sends_auth_headers(settings: Settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["apptoken"] == "test-token"
        assert request.headers["appPlatform"] == "web"
        assert request.headers["appname"] == "com.xiaomi.hm.health"
        assert request.url.path == "/users/-/profile"
        return httpx.Response(200, json={"data": {"userId": 42, "nickname": "Tester"}})

    http = httpx.AsyncClient(
        base_url=settings.base_url,
        transport=httpx.MockTransport(handler),
        headers={
            "apptoken": settings.zepp_app_token.get_secret_value(),
            "appPlatform": settings.zepp_app_platform,
            "appname": settings.zepp_app_name,
        },
    )
    client = ZeppClient(settings, http_client=http)
    try:
        result = await client.check_connection()
    finally:
        await http.aclose()

    assert result["connected"] is True
    assert result["profile"] == {"userId": 42, "nickname": "Tester"}


@pytest.mark.asyncio
async def test_list_workouts_follows_cursor(settings: Settings) -> None:
    calls: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        cursor = request.url.params.get("trackid")
        calls.append(cursor)
        assert request.url.params["userid"] == "42"
        if cursor is None:
            payload = {
                "code": 1,
                "data": {"next": 100, "summary": [{"trackid": "a", "source": "watch"}]},
            }
        else:
            payload = {
                "code": 1,
                "data": {"next": 0, "summary": [{"trackid": "b", "source": "watch"}]},
            }
        return httpx.Response(200, json=payload)

    http = httpx.AsyncClient(
        base_url=settings.base_url,
        transport=httpx.MockTransport(handler),
    )
    client = ZeppClient(settings, http_client=http)
    try:
        result = await client.list_workouts(limit=2)
    finally:
        await http.aclose()

    assert calls == [None, "100"]
    assert [item["trackid"] for item in result["items"]] == ["a", "b"]
    assert result["count"] == 2


@pytest.mark.asyncio
async def test_get_workout_uses_track_and_source(settings: Settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/sport/run/detail.json"
        assert request.url.params["trackid"] == "abc"
        assert request.url.params["source"] == "watch"
        return httpx.Response(200, json={"code": 1, "data": {"heart_rate": "1,2,3"}})

    http = httpx.AsyncClient(
        base_url=settings.base_url,
        transport=httpx.MockTransport(handler),
    )
    client = ZeppClient(settings, http_client=http)
    try:
        result = await client.get_workout(track_id="abc", source="watch")
    finally:
        await http.aclose()
    assert result == {"heart_rate": "1,2,3"}


@pytest.mark.asyncio
async def test_api_error_is_raised(settings: Settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=json.dumps({"code": -1, "message": "bad token"}))

    http = httpx.AsyncClient(
        base_url=settings.base_url,
        transport=httpx.MockTransport(handler),
    )
    client = ZeppClient(settings, http_client=http)
    try:
        with pytest.raises(ZeppApiError, match="bad token"):
            await client.get_user_profile()
    finally:
        await http.aclose()
