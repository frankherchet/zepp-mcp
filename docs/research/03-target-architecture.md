# Target architecture

## Design goals

The server should be:

- self-hosted;
- FastMCP-based;
- transport-agnostic at the tool layer;
- usable from Codex, Claude and other standard MCP clients;
- read-only initially;
- structured-data first;
- tolerant of Zepp API drift;
- easy to test without live Zepp credentials.

## FastMCP transport strategy

FastMCP supports the two relevant deployment styles from the same server definition.

### Local/client-managed: stdio

Use when an MCP client launches the process directly.

```python
mcp.run(transport="stdio", show_banner=False)
```

This is the simplest integration pattern for local clients and should remain supported even when HTTP deployment is added.

### Self-hosted: Streamable HTTP

Use for one persistent MCP service reachable by multiple clients.

Typical FastMCP deployment:

```python
mcp.run(transport="http", host="127.0.0.1", port=8000)
```

The default MCP path is `/mcp` in current FastMCP. For actual remote exposure, put the server behind TLS/reverse proxy and authentication rather than binding an unauthenticated service directly to the public internet.

The application should not define different tool catalogs for stdio and HTTP.

## Suggested layers

```text
MCP client
   |
FastMCP server / tool schemas
   |
ZeppService (semantic operations)
   |
ZeppClient (HTTP endpoint calls)
   |
AuthProvider + regional host configuration
   |
Zepp/Huami private cloud API
```

Decoders/models sit between client and service:

```text
raw response -> decoder -> normalized Pydantic model -> tool result
```

## Suggested modules

### `config.py`

Responsibilities:

- load environment overrides;
- load local config from platform-appropriate config directory;
- validate token/user id/base URL;
- mask secrets for `config show`;
- enforce restrictive permissions on local credential files where supported.

Suggested settings:

```text
ZEPP_APP_TOKEN
ZEPP_USER_ID
ZEPP_BASE_URL
ZEPP_REQUEST_TIMEOUT_MS
ZEPP_RAW_RESPONSES=false
```

Later optional settings:

```text
ZEPP_AUTH_PROVIDER=token|password|...
ZEPP_EMAIL
ZEPP_PASSWORD
```

Do not require account password in the initial release.

### `auth.py`

Use a small interface even if the first implementation has only static-token auth.

Example conceptual protocol:

```python
class AuthProvider(Protocol):
    async def credentials(self) -> ZeppCredentials: ...
    async def refresh(self) -> ZeppCredentials: ...
```

This isolates future login/cookie/token-refresh experiments from the HTTP client.

### `client.py`

Async `httpx.AsyncClient` wrapper responsible for:

- shared headers (`apptoken`, app metadata when required);
- timeout;
- regional base URL;
- request/response error mapping;
- endpoint-specific request methods;
- optional raw response capture for tests/debugging;
- no MCP imports.

Use explicit methods rather than a public arbitrary-URL requester for the initial public tool surface.

### `decoding.py`

Pure functions for:

- base64 JSON;
- base64 binary heart-rate/activity blobs;
- nested JSON strings;
- workout detail series;
- timestamp normalization.

Pure decoding functions are easy to fixture-test and should not access config/network.

### `models.py`

Pydantic models should be permissive around undocumented fields. Prefer:

- known typed fields;
- `extra="allow"` for raw API compatibility;
- nullable fields for sport/device-specific values;
- stable normalized public models separate from exact raw models where needed.

Do not copy the full historical workout schema as mandatory fields.

### `service.py`

Optional but useful boundary for operations involving multiple API calls, e.g.:

- retrieve workout history then detail;
- combine daily health + derived event metrics;
- resolve a workout by date/title-like characteristics;
- paginate history safely.

### `server.py`

Responsibilities only:

- create `FastMCP` server;
- register tools;
- validate simple MCP inputs;
- assign tool annotations/tags;
- acquire an injected/runtime service/client;
- return structured results.

Reuse the Paperless pattern:

```python
def create_server(client: ZeppClient | None = None) -> FastMCP:
    ...
```

### `cli.py`

Commands should likely be:

```text
zepp-mcp serve
zepp-mcp setup
zepp-mcp config show
zepp-mcp config reset
zepp-mcp doctor
```

`doctor` can validate token, user id, regional endpoint and one lightweight API request without exposing secrets.

## Packaging/toolchain

Recommended baseline based on the existing Paperless project:

- Python >= 3.11
- Hatchling
- uv
- FastMCP 3.x
- httpx
- Pydantic 2
- platformdirs
- pytest / pytest-asyncio
- Ruff
- strict mypy

A FIT parsing dependency is not required just to access Zepp cloud workouts. Add one only if the MCP later accepts local FIT files or obtains original FIT blobs from an endpoint.

## Logging

Never log:

- `apptoken`;
- password;
- Authorization-like headers;
- full raw profile payloads at normal log levels.

Debug HTTP logging should redact credentials. MCP stdio mode must send logs to stderr, never stdout.

## Error model

Map unstable backend behavior to compact typed errors/messages such as:

- authentication expired/invalid;
- regional host mismatch;
- endpoint unavailable;
- rate-limited;
- malformed/unrecognized payload;
- workout not found.

Do not silently swallow exceptions as the existing small `imastarboy97/zepp-mcp` server sometimes does. A caller needs to know whether data is absent or the API call failed.

## Compatibility principle

Compatibility with Codex vs Claude should come from adherence to MCP, not client-specific code. Keep tool schemas ordinary JSON-schema-compatible types and use standard `structuredContent`. Avoid assuming a client will parse Markdown tables or custom text protocols.
