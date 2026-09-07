# AGENTS.md

## Project intent

Build a small, self-hosted, read-first FastMCP server for Zepp/Amazfit data that works with
Codex, Claude and other MCP clients. Keep Zepp API quirks in the HTTP client layer and keep MCP
tools thin, typed and generic.

## Development rules

- Python 3.11+ and `uv`.
- FastMCP 3.x.
- Async HTTP through `httpx.AsyncClient`.
- Never log or return the Zepp app token.
- Local credential files must remain user-only on POSIX.
- Do not add write/mutation endpoints without an explicit safety design.
- The Zepp API is reverse engineered; isolate endpoint assumptions and test with fixtures.
- Prefer structured MCP results over formatted prose.
- Run `ruff format`, `ruff check`, `mypy`, and `pytest` before merging.

## Architecture

- `config.py`: validated settings and credential storage.
- `client.py`: Zepp HTTP/API behavior.
- `server.py`: FastMCP tools only.
- `cli.py`: setup/config and stdio/http launch.
- `docs/research/`: source material and architectural decisions.
