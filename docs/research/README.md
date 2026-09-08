# Zepp MCP research index

This directory captures the technical research for a self-hosted Zepp MCP server.

Goal: build a generic, read-oriented MCP server on top of FastMCP that works with MCP clients such
as Codex and Claude, with both local `stdio` and self-hosted Streamable HTTP deployment options.

## Documents

- [00-repository-inventory.md](00-repository-inventory.md) — current repository state and scope.
- [01-reference-implementation-paperless.md](01-reference-implementation-paperless.md) — patterns worth reusing from `local-paperless-ngx-mcp`.
- [02-zepp-api-landscape.md](02-zepp-api-landscape.md) — known Zepp/Huami endpoints, authentication options, workout data and caveats.
- [03-target-architecture.md](03-target-architecture.md) — proposed FastMCP architecture, transports, configuration and API layering.
- [04-proposed-tool-surface.md](04-proposed-tool-surface.md) — generic MCP tool catalog and data-model recommendations.
- [05-risks-and-next-steps.md](05-risks-and-next-steps.md) — uncertainties, validation plan and implementation sequence.
- [06-auth-flow.md](06-auth-flow.md) — implemented login providers, regional Zepp v2 flow, legacy fallback and credential handling.

## Executive summary

The repository started without an implementation, so there was no legacy code to preserve. The
strongest reusable foundation is the architecture of `frankherchet/local-paperless-ngx-mcp`:
separate CLI/config/client/server modules, FastMCP tools returning structured data, dependency
injection for tests, strict typing, `uv`, and explicit local credential handling.

For Zepp, there is no official public API. The practical interface is the private Huami/Zepp cloud
API used by the app and web portal. Recent community projects confirm useful endpoints for daily
health data, events/training load, sport history, sport detail, profile and device metadata.
Authentication remains the least stable part. The implementation therefore keeps the runtime API
client token-based while providing a pluggable one-time login provider during setup; manual
`apptoken` + user ID configuration remains available as a fallback.

For client compatibility, implement the server itself independently of transport. Offer `stdio` for
locally spawned clients and Streamable HTTP for a persistent self-hosted service. FastMCP supports
both from the same server definition.

The initial implementation should stay read-only and generic: expose raw/normalized API data and
workout detail rather than embedding training advice or domain-specific analysis into the server.
Higher-level agents can derive analysis from those tools.
