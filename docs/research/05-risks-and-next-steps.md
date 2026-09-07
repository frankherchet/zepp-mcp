# Risks, open questions and next steps

## Main risks

### 1. Private API instability

Zepp/Huami endpoints are undocumented and may change without notice. Hostnames, required headers, schemas and auth flows have already changed across community implementations.

Mitigation:

- isolate all endpoint logic in `client.py`;
- keep decoders fixture-tested;
- use tolerant models;
- surface clear endpoint/auth errors;
- keep raw payload fixtures with secrets removed;
- document known-good device/account/region combinations.

### 2. Authentication lifecycle

`apptoken` is practical but expires. Automated password login exists in some projects but appears less reliable in recent reports.

Mitigation:

- first release: manual token + user id + base URL;
- `doctor` detects expired credentials;
- setup/config commands make replacement easy;
- define an auth-provider seam before adding experimental login refresh;
- never require storing a Zepp password for normal use.

### 3. Regional routing

Accounts can use different `api-mifit-*.zepp.com` hosts. A token may be valid but the wrong host can yield confusing failures.

Mitigation:

- make base URL explicit and persisted;
- consider a small known-region mapping only as setup assistance;
- do not silently bounce requests across arbitrary regions;
- report the effective host in `zepp_status`.

### 4. Schema differences by sport/device

Workout summaries contain many optional sport-specific fields. Detail series formats can vary by version/device/sport.

Mitigation:

- avoid rigid all-required models;
- retain unknown fields;
- test at least strength training plus one GPS activity before claiming general support;
- make normalization additive: unknown raw data should remain accessible.

### 5. Health-data privacy

The MCP exposes highly personal health data. A self-hosted HTTP service without auth would be inappropriate outside localhost.

Mitigation:

- default HTTP bind to `127.0.0.1`;
- document TLS/reverse-proxy/auth requirements for LAN/remote access;
- never log tokens;
- keep profile tools minimal by default;
- avoid telemetry in the MCP package unless explicitly opted in.

## Open research questions

### Workout FIT availability

We know the Zepp app can export a workout as FIT, but it is not yet established whether the cloud API exposes the original FIT binary directly or whether the app constructs it from `/v1/sport/run/detail.json` and related data.

Research task:

- capture the network transaction while exporting/sharing FIT from the Zepp app;
- determine whether a download URL/endpoint exists;
- compare cloud detail data with FIT `record`, `lap`, `session` and developer fields.

### Strength training template APIs

The shared training-template URLs use Zepp-hosted JSON/data on S3, and the FIT workout itself does not appear to carry exercise names/weights. We need to discover whether templates and executed strength-set data have an authenticated API.

Research task:

- capture app traffic while opening/editing/syncing a training template;
- capture traffic during/after strength workout sync;
- search for template ids, exercise ids, group/set/repetition data;
- compare share-template payload with authenticated responses.

### Endpoint headers

Some endpoints need app-specific headers such as `appPlatform`/`appname`; some combinations trigger encrypted responses.

Research task:

- establish a minimal known-good header set per endpoint family;
- record failures and response content types;
- prefer web-style non-encrypted responses where possible.

### Pagination semantics

Workout history uses a `trackid`/`next` style in older exporter code. Need to confirm current behavior with a 2026 account and date filtering.

### Rate limiting

Public community documentation is incomplete. The client should be conservative until limits are measured.

## Recommended implementation sequence

### Milestone 0 — project skeleton

Copy architectural conventions, not code, from `local-paperless-ngx-mcp`:

- `pyproject.toml` + `uv`;
- package layout;
- CLI/config handling;
- FastMCP server factory;
- Ruff/mypy/pytest;
- CI;
- `AGENTS.md`, `SECURITY.md`, README.

No Zepp password auth yet.

### Milestone 1 — authentication + status

Implement:

- static `apptoken` auth provider;
- regional base URL config;
- `ZeppClient` with redacted errors/logging;
- `zepp_status` / `doctor` using a lightweight authenticated endpoint.

Success criterion: repeatable setup on the target European Zepp account without app-password storage.

### Milestone 2 — workouts first

Implement and fixture-test:

- `list_workouts` via `/v1/sport/run/history.json`;
- pagination;
- `get_workout` via `/v1/sport/run/detail.json`;
- initial detail-series decoders;
- raw opt-in for unsupported fields.

This directly unlocks the training-analysis use case.

### Milestone 3 — daily health/events

Implement:

- daily band data;
- sleep/heart-rate decoding;
- generic events;
- training load / sport load / VO2 max convenience calls.

### Milestone 4 — strength-training metadata

Only after network research confirms authoritative endpoints, add training-template/exercise metadata tools.

### Milestone 5 — HTTP deployment hardening

Support/configure Streamable HTTP in addition to stdio. Add deployment documentation and an auth story appropriate for self-hosting.

## Acceptance criteria for a useful v0.1

A first useful release does not need every Zepp metric. It should:

1. install cleanly with `uv`/wheel;
2. support `stdio` from both Codex/Claude-style local clients;
3. support a self-hosted Streamable HTTP launch mode;
4. store an `apptoken` safely enough for a local tool and never expose it;
5. list workout history with pagination;
6. retrieve one workout's detailed time series;
7. return structured JSON-compatible results;
8. have fixture-based tests that require no live account;
9. fail clearly on expired tokens or API drift.

## Source links used during this research

- FastMCP documentation: https://gofastmcp.com/
- Existing project reference: https://github.com/frankherchet/local-paperless-ngx-mcp
- Existing Zepp MCP: https://github.com/imastarboy97/zepp-mcp
- Recent Zepp API mapping: https://github.com/EvanCooke/zepp-export
- Workout history/detail implementation: https://github.com/rolandsz/Mi-Fit-and-Zepp-workout-exporter
- Recent auth/health CLI: https://github.com/m4ary/zepp-health-cli
- Additional recent Python client: https://github.com/Baitinq/amazfit-cli
