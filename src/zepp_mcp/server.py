"""FastMCP server exposing read-only Zepp health/workout data."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from zepp_mcp import __version__
from zepp_mcp.client import JsonObject, ZeppClient
from zepp_mcp.config import get_settings

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True)


def create_server(client: ZeppClient | None = None) -> FastMCP:
    """Create the MCP server, optionally injecting a client for tests."""
    server = FastMCP(
        name="Zepp",
        version=__version__,
        instructions=(
            "Read Zepp/Amazfit health and workout data through a reverse-engineered API. "
            "All tools are read-only. Workout list results provide track_id/source values "
            "required by get_workout."
        ),
    )

    @asynccontextmanager
    async def use_client() -> AsyncIterator[ZeppClient]:
        if client is not None:
            yield client
            return
        async with ZeppClient(get_settings()) as runtime_client:
            yield runtime_client

    @server.tool(annotations=READ_ONLY, tags={"zepp", "status"})
    async def zepp_status() -> JsonObject:
        """Verify Zepp authentication and return a compact connection/profile summary."""
        async with use_client() as zepp:
            return await zepp.check_connection()

    @server.tool(annotations=READ_ONLY, tags={"zepp", "workouts", "list"})
    async def list_workouts(
        cursor_track_id: str | None = None,
        page_count: int = 1,
    ) -> JsonObject:
        """List recent workouts as one or more complete Zepp history pages.

        Pass next_track_id from a previous response as cursor_track_id to continue.
        Each item includes the trackid and source needed by get_workout.
        """
        if not 1 <= page_count <= 10:
            raise ValueError("page_count must be between 1 and 10")
        async with use_client() as zepp:
            return await zepp.list_workouts(
                cursor_track_id=cursor_track_id, page_count=page_count
            )

    @server.tool(annotations=READ_ONLY, tags={"zepp", "workouts", "detail"})
    async def get_workout(track_id: str, source: str) -> JsonObject:
        """Return the detailed Zepp payload for one workout.

        Use trackid and source from list_workouts. The detail can contain HR trace,
        timing, laps, GPS/pace fields and sport-specific metrics depending on activity.
        """
        async with use_client() as zepp:
            return await zepp.get_workout(track_id=track_id, source=source)

    return server


mcp = create_server()
