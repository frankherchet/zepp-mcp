# Zepp / Huami API landscape

## Status

Zepp does not provide a documented public consumer API for the data used by the mobile app. Community tools therefore rely on private Huami/Zepp cloud endpoints and reverse engineering. The API is useful but must be treated as unstable.

Important consequence: the MCP should expose a stable internal model while isolating endpoint-specific behavior in the client layer.

## Authentication

### Recommended initial approach: existing `apptoken`

Recent community tools commonly use an `apptoken` bearer-style header plus a numeric user id and a regional API host. A practical way to obtain these is from the logged-in Zepp/Huami privacy web portal or captured app traffic.

This should be the supported v1 setup flow because it is simple, testable and does not require storing the Zepp account password.

Suggested configuration:

```text
ZEPP_APP_TOKEN=...
ZEPP_USER_ID=...
ZEPP_BASE_URL=https://api-mifit-de2.zepp.com
```

The base URL varies by account/region. Known examples from community implementations include:

- `https://api-mifit.huami.com`
- `https://api-mifit-us2.zepp.com`
- `https://api-mifit-de2.zepp.com`

Do not hard-code US endpoints in the core client.

### Email/password login is possible but fragile

`imastarboy97/zepp-mcp` implements a two-step login using AES-encrypted credentials against `/v2/registrations/tokens`, followed by `/v2/client/login`, then caches the resulting app token and user id.

However, newer community projects explicitly report that password login flows are unreliable/deprecated/rate-limited and recommend using an already-issued `apptoken`. Therefore the architecture should support auth providers, but automatic password login should be optional and experimental rather than foundational.

## Endpoint families discovered in current community projects

### Daily band/health data

Common endpoint:

```text
GET /v1/data/band_data.json
```

Typical parameters include:

- `userid`
- `from_date`
- `to_date`
- `query_type=detail`
- device/app metadata

Responses can include:

- base64 JSON summaries
- base64 binary heart-rate blobs
- activity/step/sleep data

A decoder layer is required.

### Events

Current implementations document both legacy and v2 event endpoints.

```text
GET /v2/users/me/events
GET /users/{userId}/events
```

Observed event categories include:

- training load / exertion (`atl`, `ctl`, `tsb`, recovery factor)
- PHN/TRIMP daily analysis
- training plan data
- post-workout recovery heart rate
- stress/emotion data
- blood pressure where supported
- daily health summaries

The event API is valuable because it exposes derived Zepp metrics that would be difficult to reconstruct locally.

### Watch sport statistics

Observed endpoint family:

```text
GET /v2/watch/users/{userId}/WatchSportStatistics/{metric}
```

Known metrics include:

- `SPORT_LOAD`
- `VO2_MAX`

Sport-load responses may include current-day load, weekly sum, optimal range and overreaching threshold.

### Workout history

Long-standing community exporters use:

```text
GET /v1/sport/run/history.json
```

The endpoint is not limited to literal running; it is the historical activity feed used for multiple sport types.

A common pagination method is `trackid`, where the API response provides a `next` cursor and summaries contain fields such as:

- `trackid`
- `source`
- workout `type` / `sport_mode`
- distance
- calories
- runtime/end time
- average/max/min heart rate
- cadence/frequency/stride-related values
- sport-specific fields such as swimming, rope skipping, altitude and training effect

Models must allow unknown/optional fields because the schema differs across sport types and device generations.

### Workout detail

Observed endpoint:

```text
GET /v1/sport/run/detail.json?trackid=...&source=...
```

Community models show detailed string-encoded series including:

- heart rate
- time
- pause data
- GPS longitude/latitude
- altitude
- pace/speed
- distance
- lap data
- cadence
- SpO2
- air-pressure altitude
- sport-specific telemetry

This endpoint is likely the key primitive for training analysis. The MCP should preserve both normalized summaries and optionally raw detail fields until all encodings are understood.

### Profile and device metadata

Observed endpoints include:

```text
GET /users/-/profile
GET /users/-/properties
GET /device/settings/meta
```

These can support user/device metadata tools but are lower priority than workout/history endpoints.

## Response encoding patterns

Community reverse engineering consistently shows multiple encodings:

1. ordinary JSON;
2. base64-encoded JSON;
3. base64-encoded binary arrays/blobs;
4. JSON strings nested inside JSON fields;
5. endpoint-specific delimited/string time series.

Some app headers can cause encrypted binary responses. Community documentation notes that web-style request metadata can avoid this for certain endpoints.

The client should therefore separate:

```text
HTTP request -> raw JSON -> endpoint decoder -> normalized model
```

Do not bury decoding inside MCP tool functions.

## Relevant community sources

### `imastarboy97/zepp-mcp`

https://github.com/imastarboy97/zepp-mcp

Useful for:

- existing MCP precedent;
- password-login implementation;
- band data decoding;
- stress/sleep/heart-rate endpoint examples.

Limitations:

- uses `mcp.server.fastmcp.FastMCP` rather than standalone modern FastMCP;
- hard-coded US auth endpoints;
- formatted-string tool outputs rather than generic structured data;
- no workout-history tool surface;
- broad exception swallowing in server functions;
- auth/password flow is a stability risk.

### `EvanCooke/zepp-export`

https://github.com/EvanCooke/zepp-export

Especially valuable because it contains a recent API reference and mapping guide based on captured Zepp traffic. It documents daily data, event APIs, sport statistics and sport history/detail.

### `rolandsz/Mi-Fit-and-Zepp-workout-exporter`

https://github.com/rolandsz/Mi-Fit-and-Zepp-workout-exporter

Useful concrete workout models and calls:

- `/v1/sport/run/history.json`
- `/v1/sport/run/detail.json`
- `trackid` pagination
- detailed workout fields

### `m4ary/zepp-health-cli`

https://github.com/m4ary/zepp-health-cli

Important auth lesson: recommends extracting `apptoken`, user id and regional host from captured traffic because newer password login flows are unreliable.

### `Baitinq/amazfit-cli`

https://github.com/Baitinq/amazfit-cli

Another recent Python client documenting health data and workout history with `apptoken`/user-id based access.

## API design implication

The MCP should not simply mirror URL paths as tools. It should define stable semantic operations (`list_workouts`, `get_workout_detail`, `list_events`, etc.), while exposing an optional low-level/raw mode for research and forward compatibility.
