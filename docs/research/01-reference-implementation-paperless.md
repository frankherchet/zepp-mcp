# Reference implementation: `local-paperless-ngx-mcp`

Repository: https://github.com/frankherchet/local-paperless-ngx-mcp

The Paperless MCP is a strong local reference because it already solves many concerns that are independent of the backend API.

## Patterns worth reusing

### 1. Separate transport/tool layer from API client

`server.py` defines MCP tools and input validation, while `client.py` owns HTTP behavior. This keeps MCP-specific code thin and makes the underlying API client reusable and testable.

Recommended for Zepp:

- `client.py`: HTTP requests, auth headers, endpoint paths, retries/error mapping.
- `decoding.py`: base64/binary/string-in-JSON normalization.
- `server.py`: tool definitions only; no hard-coded HTTP URLs.

### 2. Server factory with client injection

Paperless uses `create_server(client: PaperlessClient | None = None)` and creates a runtime client only when one was not injected. This is excellent for unit tests because tool behavior can be tested against a fake client without network traffic.

Reuse this pattern directly.

### 3. FastMCP as the server implementation

Paperless currently uses `fastmcp>=3.4.4,<4` and `FastMCP` from the standalone `fastmcp` package rather than `mcp.server.fastmcp`. For a new project, prefer the standalone FastMCP package and avoid copying older examples that import FastMCP from the MCP Python SDK.

### 4. Structured tool results

The Paperless MCP deliberately returns compact Python dict/list structures rather than formatted prose. This is the right model for Zepp as well. Health and workout data should be machine-readable so Codex, Claude and other clients can perform their own analysis.

Recommended rule: MCP tools return normalized structured content by default, with raw payloads opt-in where useful.

### 5. Tool annotations and tags

Paperless declares `ToolAnnotations` for read-only/write/destructive behavior and adds tags to tools. This gives clients useful metadata and should be carried over.

The first Zepp implementation should mark every tool read-only.

### 6. Explicit configuration and credential hygiene

Paperless has a CLI-driven setup flow, a local config file, `0600` permissions on Unix-like systems, masked `config show`, and explicit environment-variable overrides. It never silently scans `.env` files at runtime.

This is especially important for Zepp because `apptoken` is effectively a bearer credential.

Recommended Zepp precedence:

1. explicit environment variables;
2. local config created by `zepp-mcp setup`;
3. otherwise fail with a clear setup message.

Suggested initial credential fields:

- `ZEPP_APP_TOKEN`
- `ZEPP_USER_ID`
- `ZEPP_BASE_URL` or region

Optional later fields for pluggable login flows should not be required by the core client.

### 7. Interactive setup must not corrupt MCP stdio

Paperless distinguishes interactive terminal startup from non-interactive MCP startup. This matters because stdout is protocol traffic under stdio.

Reuse the same behavior: setup may be interactive only from an explicit CLI command or interactive TTY, never by printing prompts into an active MCP stdio session.

### 8. `uv` + `pyproject.toml` + strict tooling

The reference project uses:

- Python >= 3.11
- `uv`
- Hatchling build backend
- Ruff
- strict mypy
- pytest + pytest-asyncio
- console-script entry point

This stack is appropriate for `zepp-mcp` with likely dependencies:

- `fastmcp>=3,<4`
- `httpx>=0.28,<1`
- `pydantic>=2,<3`
- `platformdirs>=4,<5`
- optionally `fitdecode` or `fitparse` only if local FIT parsing becomes part of the server

### 9. Small, generic MCP surface over backend primitives

Paperless has domain-aware tools but keeps them close to API capabilities. For Zepp, avoid returning pre-written wellness recommendations. Prefer tools such as `list_workouts`, `get_workout`, `get_daily_health`, `list_events`, etc.

## Patterns not to copy blindly

Paperless has a stable documented REST API and a durable API token model; Zepp does not. Therefore:

- endpoint availability must be feature-detected or fail gracefully;
- response models need tolerant parsing;
- region/host handling is first-class;
- auth should be replaceable;
- raw payload access is more valuable during reverse engineering;
- fixtures should capture multiple real response variants.

## Useful implementation references in the Paperless repo

- `src/paperless_ngx_mcp/cli.py`: setup/serve/config behavior.
- `src/paperless_ngx_mcp/config.py`: local config and environment handling.
- `src/paperless_ngx_mcp/client.py`: isolated async HTTP client.
- `src/paperless_ngx_mcp/server.py`: FastMCP factory, annotations, validation and injected client.
- `pyproject.toml`: packaging and quality-tool configuration.
- `fastmcp.json`: development runner configuration.
