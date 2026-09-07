# Zepp MCP

Self-hosted [FastMCP](https://gofastmcp.com/) server for Zepp/Amazfit health and workout data.
The Zepp API is not public; this project wraps reverse-engineered read endpoints behind a small,
typed MCP surface that can be used by Codex, Claude and other MCP clients.

## Current v0.1 scope

- Local setup with `apptoken`, Zepp user ID and configurable regional API base URL.
- Secure local config file (`0600` on POSIX) or explicit environment overrides.
- `stdio` transport for locally launched MCP clients.
- Streamable HTTP transport for self-hosting.
- Read-only tools:
  - `zepp_status`
  - `list_workouts`
  - `get_workout`

See `docs/research/` for the API/architecture assessment and known unknowns.

## Requirements

- Python 3.11+
- `uv`
- A Zepp `apptoken` and user ID

The initial version deliberately does not automate email/password login. Authentication is kept
pluggable while the token-based API surface is validated across regions/accounts.

## Install for development

```bash
git clone https://github.com/frankherchet/zepp-mcp.git
cd zepp-mcp
uv sync --extra dev
uv run zepp-mcp setup
```

The setup wizard asks for:

1. Zepp API base URL (default `https://api-mifit.zepp.com`)
2. Zepp user ID
3. Zepp app token (hidden input)

It verifies the credentials against the Zepp profile endpoint before saving them.

## Run over stdio

```bash
uv run zepp-mcp serve
```

or directly through FastMCP:

```bash
uv run fastmcp run fastmcp.json
```

Example MCP client configuration:

```json
{
  "mcpServers": {
    "zepp": {
      "command": "uv",
      "args": ["run", "--directory", "/absolute/path/to/zepp-mcp", "zepp-mcp", "serve"]
    }
  }
}
```

## Run as self-hosted HTTP MCP

```bash
uv run zepp-mcp serve --transport http --host 0.0.0.0 --port 8000
```

For deployment, put TLS/authentication in front of the MCP endpoint unless the server is only
reachable on a trusted private network. The Zepp credentials are server-side and are never
returned by the MCP tools.

## Environment configuration

Headless deployments can use environment variables instead of the local config file:

```bash
export ZEPP_APP_TOKEN='...'
export ZEPP_USER_ID='...'
export ZEPP_BASE_URL='https://api-mifit.zepp.com'
uv run zepp-mcp serve --transport http --host 0.0.0.0 --port 8000
```

`ZEPP_APP_TOKEN` and `ZEPP_USER_ID` must be supplied together when overriding credentials.
Optional variables are `ZEPP_REQUEST_TIMEOUT_MS`, `ZEPP_APP_NAME`, and `ZEPP_APP_PLATFORM`.

Inspect the current local config without exposing the full token:

```bash
uv run zepp-mcp config show
```

Remove it with:

```bash
uv run zepp-mcp config reset
```

## MCP tools

### `zepp_status`

Checks authentication through `/users/-/profile` and returns a compact profile/connection summary.

### `list_workouts(cursor_track_id=null, limit=20)`

Reads `/v1/sport/run/history.json`, follows Zepp's track-ID cursor as needed, and returns workout
summaries plus `next_track_id`. Each summary contains the `trackid` and `source` used for detail.

### `get_workout(track_id, source)`

Reads `/v1/sport/run/detail.json`. Depending on the workout it can contain heart-rate trace,
timing, laps, GPS/pace fields and sport-specific metrics.

## Development

```bash
uv run ruff format .
uv run ruff check .
uv run mypy
uv run pytest
```

The next implementation milestones are health/events endpoints, training-load data, FIT/download
discovery and strength-training/template discovery.
