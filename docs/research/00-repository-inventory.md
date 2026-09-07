# Repository inventory

## `frankherchet/zepp-mcp`

State at the start of research (2026-09-07):

- default branch: `main`
- initial commit only
- repository contents: `LICENSE`
- no Python package, README, CI, tests, FastMCP config or application code yet

This is useful because the project can adopt a clean structure without migration constraints.

## Intended scope

The requested target is a self-hosted MCP server that:

1. uses FastMCP;
2. exposes available Zepp/Huami API operations generically rather than hard-coding a single coaching workflow;
3. can be used from different MCP clients, notably Codex and Claude;
4. supports personal health/workout use cases, especially workout history/detail and FIT-like time-series information where the cloud API exposes it;
5. follows good operational patterns from `local-paperless-ngx-mcp` where applicable.

## Proposed non-goals for the first implementation

- Do not implement a fitness coach inside the MCP server.
- Do not make undocumented writes to Zepp until read APIs and authentication are stable.
- Do not depend on one specific Amazfit model in the public tool schemas.
- Do not expose credentials, raw auth responses or tokens through MCP results/logs.
- Do not make email/password login the only authentication path.

## Repository structure to aim for

A likely initial structure, intentionally close to `local-paperless-ngx-mcp`:

```text
zepp-mcp/
├── README.md
├── LICENSE
├── AGENTS.md
├── SECURITY.md
├── pyproject.toml
├── uv.lock
├── fastmcp.json
├── docs/
│   └── research/
├── src/
│   └── zepp_mcp/
│       ├── __init__.py
│       ├── cli.py
│       ├── config.py
│       ├── client.py
│       ├── models.py
│       ├── decoding.py
│       ├── responses.py
│       └── server.py
└── tests/
    ├── fixtures/
    ├── test_client.py
    ├── test_config.py
    ├── test_decoding.py
    └── test_server.py
```

The exact split should stay modest. Zepp has several response encodings and endpoint families, so a dedicated `decoding.py` is more justified here than in many ordinary REST clients.
