# Zepp MCP

Self-hosted [FastMCP](https://gofastmcp.com/) server for Zepp/Amazfit health and workout data.
The Zepp API is not public; this project wraps reverse-engineered read endpoints behind a small,
typed MCP surface that can be used by Codex, Claude and other MCP clients.

## Current v0.1 scope

- Interactive Zepp account login that exchanges account/password for `apptoken` + user ID.
- Manual token setup remains available as a fallback.
- The account password is never written to the config file.
- Secure local config file (`0600` on POSIX) or explicit environment overrides.
- `stdio` transport for locally launched MCP clients.
- Streamable HTTP transport for self-hosting.
- Read-only tools:
  - `zepp_status`
  - `list_workouts`
  - `get_workout`

See `docs/research/` for the API/authentication assessment and known unknowns.

## Requirements

- Python 3.11+
- `uv`
- A Zepp/Amazfit account, or an existing Zepp `apptoken` + user ID

## Install for development

```bash

git clone https://github.com/frankherchet/zepp-mcp.git
cd zepp-mcp
uv sync --extra dev
```

## Setup with your Zepp account

The normal setup path is now account login:

```bash
uv run zepp-mcp setup
```

For a new configuration, press Enter to select `login`. Setup asks for:

1. account country code such as `DE` or `US`;
2. Zepp account email or phone number (phone numbers should use international format);
3. Zepp password via hidden terminal input.

The password is sent only to the Zepp/Huami authentication endpoint, held in memory for the login,
and is **not persisted**. Successful login stores only the returned app token, user ID, API base URL
and non-secret client settings in the local config file.

The login provider first uses the current regional Zepp v2 flow. `--region auto` selects the EU or US
cluster from the country code. If that protocol is unavailable, it falls back to the historical Huami
account flow. Explicit credential rejection or HTTP 429 rate limiting does not trigger a second
password attempt.

If the account lives on a different cluster than expected, retry explicitly:

```bash
uv run zepp-mcp setup --auth login --country-code DE --region eu
uv run zepp-mcp setup --auth login --country-code US --region us
```

Because Zepp does not publish this API, the login protocol can change without notice. Manual token
setup remains available for that reason:

```bash
uv run zepp-mcp setup --auth token
```

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
reachable on a trusted private network. The Zepp credentials are server-side and are never returned
by the MCP tools.

## Environment configuration

Headless deployments can use environment variables instead of the local config file:

```bash
export ZEPP_APP_TOKEN='...'
export ZEPP_USER_ID='...'
export ZEPP_BASE_URL='https://api-mifit-de2.zepp.com'
uv run zepp-mcp serve --transport http --host 0.0.0.0 --port 8000
```

`ZEPP_APP_TOKEN` and `ZEPP_USER_ID` must be supplied together when overriding credentials. Optional
variables are `ZEPP_BASE_URL`, `ZEPP_REQUEST_TIMEOUT_MS`, `ZEPP_APP_NAME`, and `ZEPP_APP_PLATFORM`.

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

Checks authentication through the workout-history endpoint and returns a compact connection summary.

### `list_workouts(cursor_track_id=null, page_count=1)`

Reads `/v1/sport/run/history.json` one Zepp page at a time. Each summary contains the `trackid` and
`source` used for workout detail. Pass the returned `next_track_id` as `cursor_track_id` to continue.

### `get_workout(track_id, source)`

Reads `/v1/sport/run/detail.json`. Depending on the workout it can contain heart-rate trace, timing,
laps, GPS/pace fields and sport-specific metrics.

## Development

```bash
uv run ruff format .
uv run ruff check .
uv run mypy
uv run pytest
```

The next implementation milestones are health/events endpoints, training-load data, FIT/download
discovery and strength-training/template discovery.
