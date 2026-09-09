"""Asynchronous client for the reverse-engineered Zepp/Huami HTTP API."""

from __future__ import annotations

import time
from types import TracebackType
from typing import Any, TypeAlias
from uuid import uuid4

import httpx

from zepp_mcp.config import Settings

JsonObject: TypeAlias = dict[str, Any]

WORKOUT_HISTORY_COUNT = "20"


class ZeppApiError(RuntimeError):
    """Raised when Zepp returns an API-level error response."""


class ZeppClient:
    """Small read-only Zepp API client.

    The API is not publicly documented by Zepp. Keep endpoint-specific behavior in
    this class so the MCP tool layer stays transport- and client-agnostic.
    """

    def __init__(self, settings: Settings, http_client: httpx.AsyncClient | None = None):
        self.settings = settings
        self._owns_http_client = http_client is None
        self._http = http_client or httpx.AsyncClient(
            base_url=settings.base_url,
            timeout=settings.timeout_seconds,
            headers={
                "apptoken": settings.zepp_app_token.get_secret_value(),
                "appPlatform": settings.zepp_app_platform,
                "appname": settings.zepp_app_name,
                "accept": "application/json",
            },
        )

    async def __aenter__(self) -> ZeppClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._owns_http_client:
            await self._http.aclose()

    async def check_connection(self) -> JsonObject:
        """Verify credentials against the workout endpoint used by this MCP."""
        workouts = await self.list_workouts()
        return {
            "connected": True,
            "user_id": self.settings.zepp_user_id,
            "base_url": self.settings.base_url,
            "workout_count_on_first_page": workouts["count"],
        }

    async def list_workouts(
        self,
        *,
        cursor_track_id: str | None = None,
        page_count: int = 1,
    ) -> JsonObject:
        """List one or more complete workout-history pages.

        Zepp exposes a track-id cursor and returns a fixed-size page from the current app API.
        """
        if not 1 <= page_count <= 10:
            raise ValueError("page_count must be between 1 and 10")

        collected: list[JsonObject] = []
        cursor = cursor_track_id or str(int(time.time()))
        next_cursor: str | None = None
        seen_cursors: set[str] = set()

        for _ in range(page_count):
            params = {
                "r": str(uuid4()),
                "trackid": cursor,
                "count": WORKOUT_HISTORY_COUNT,
                "userid": self.settings.zepp_user_id,
                "type": "0",
            }
            payload = await self._get_json("v1/sport/run/history.json", params=params)
            data = payload.get("data")
            if not isinstance(data, dict):
                raise ZeppApiError("Workout history response did not contain a data object")

            summaries = data.get("summary") or []
            if not isinstance(summaries, list):
                raise ZeppApiError("Workout history data.summary was not a list")
            collected.extend(item for item in summaries if isinstance(item, dict))

            raw_next = data.get("next")
            next_cursor = str(raw_next) if raw_next not in (None, "", -1, "-1", 0, "0") else None
            if (
                not next_cursor
                or not summaries
                or next_cursor == cursor
                or next_cursor in seen_cursors
            ):
                break
            seen_cursors.add(next_cursor)
            cursor = next_cursor

        return {
            "items": collected,
            "count": len(collected),
            "pages_requested": page_count,
            "next_track_id": next_cursor,
        }

    async def get_workout(self, *, track_id: str, source: str) -> JsonObject:
        """Return Zepp's detailed payload for one workout."""
        if not track_id.strip():
            raise ValueError("track_id must not be empty")
        if not source.strip():
            raise ValueError("source must not be empty")
        payload = await self._get_json(
            "v1/sport/run/detail.json",
            params={
                "trackid": track_id.strip(),
                "source": source.strip(),
                "userid": self.settings.zepp_user_id,
            },
        )
        data = payload.get("data")
        return data if isinstance(data, dict) else payload

    async def _get_json(
        self,
        path: str,
        *,
        params: dict[str, str] | None = None,
    ) -> JsonObject:
        try:
            response = await self._http.get(path, params=params)
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            body = error.response.text[:500]
            raise ZeppApiError(
                f"Zepp API returned HTTP {error.response.status_code} for {path}: {body}"
            ) from error
        except httpx.HTTPError as error:
            raise ZeppApiError(f"Zepp API request failed for {path}: {error}") from error

        try:
            payload = response.json()
        except ValueError as error:
            raise ZeppApiError(f"Zepp API returned invalid JSON for {path}") from error
        if not isinstance(payload, dict):
            raise ZeppApiError(f"Zepp API returned a non-object response for {path}")

        code = payload.get("code")
        if code not in (None, 1, "1"):
            message = payload.get("message") or payload.get("msg") or "unknown Zepp API error"
            raise ZeppApiError(f"Zepp API error {code}: {message}")
        return payload
