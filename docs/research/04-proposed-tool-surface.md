# Proposed MCP tool surface

The first public surface should be generic, read-only and close to Zepp concepts. Analysis/coaching belongs in the consuming agent, not the data connector.

## Principles

- return structured dict/list content, not preformatted reports;
- paginate potentially large collections;
- use date ranges rather than vague `days` arguments where practical;
- preserve opaque Zepp ids (`trackid`, `source`, device source) as strings when their numeric stability is unknown;
- expose `raw`/`detail` options sparingly for reverse-engineering needs;
- avoid a generic arbitrary HTTP request tool: it would leak implementation detail and expand the security surface.

## Phase 1: essential tools

### `zepp_status`

Purpose: verify configuration/auth and report safe connection metadata.

Suggested result:

```json
{
  "authenticated": true,
  "user_id": "...masked-or-safe...",
  "base_url": "https://api-mifit-de2.zepp.com",
  "capabilities": {
    "workouts": true,
    "band_data": true,
    "events_v2": true
  }
}
```

Do not return the app token.

### `list_workouts`

Inputs:

```text
from_date?: YYYY-MM-DD
through_date?: YYYY-MM-DD
cursor?: string
limit?: int
sport_type?: int|string
```

Returns normalized workout summaries and next cursor.

Important: the underlying history API has historically used `trackid` cursor pagination. Hide that detail behind a generic `cursor` field but preserve `trackid` in each workout.

### `get_workout`

Inputs:

```text
track_id: string
source: string
include_series: bool = true
include_raw: bool = false
```

Returns:

- summary fields if available;
- normalized detailed series;
- lap/pause information where decodable;
- optional raw backend fields for unsupported/new sport metrics.

This is the highest-value tool for training analysis.

### `get_daily_health`

Inputs:

```text
date: YYYY-MM-DD
include_raw: bool = false
```

Returns normalized daily summary including available steps, sleep and heart-rate data from band data.

### `list_events`

Inputs:

```text
event_type: string
sub_type?: string
from_timestamp/date
to_timestamp/date
limit
```

This should expose the Zepp event system generically enough to access new event categories without creating a separate MCP tool for every metric.

For safety/clarity, validate event-type strings and document known values, but don't hard-code an exhaustive enum until the API is better characterized.

## Phase 2: convenience tools

These can be thin semantic wrappers around generic calls and may improve agent usability.

### `get_training_load`

Returns ATL/CTL/TSB, target/completion and recovery data where available from the v2 event API.

### `get_sport_load`

Returns daily and weekly sport load plus Zepp's optimal/overreaching ranges.

### `get_vo2_max`

Returns VO2-max records from WatchSportStatistics.

### `get_profile`

Returns a deliberately limited safe profile subset. Avoid exposing more personal data than necessary by default.

### `get_device_info`

Returns device source/model/capabilities if the endpoint is available.

## Raw vs normalized workout detail

The workout detail endpoint is especially undocumented and sport-dependent. A useful shape is:

```json
{
  "track_id": "...",
  "source": "...",
  "sport_type": 60,
  "start_time": "...",
  "duration_seconds": 2815,
  "heart_rate": [
    {"offset_seconds": 0, "bpm": 92},
    {"offset_seconds": 1, "bpm": 94}
  ],
  "pauses": [...],
  "laps": [...],
  "gps": [...],
  "metrics": {...},
  "raw": null
}
```

A stable normalized representation makes it much easier for agents to compare workouts. However, decoding should not discard unknown backend data; `include_raw=true` can include the untouched source fields when troubleshooting.

## Strength-training-specific data

Do not assume workout history/detail alone will contain exercise names, sets, repetitions or weights. In the Zepp FIT exports observed during this project, FIT contained dense heart-rate `record` data and `lap` segmentation but the exercise template/weights came from the separately shared training template.

Therefore investigate whether Zepp has separate cloud endpoints for:

- training templates;
- strength exercise definitions;
- executed set/repetition metadata;
- share-template payloads.

If these exist, add generic tools such as:

```text
list_training_templates
get_training_template
```

Do not infer exercise names from workout laps if the authoritative template is available elsewhere.

## Resource/file handling

If a future endpoint exposes an original FIT file, do not base64-encode large FIT binaries into ordinary JSON tool results. Prefer an MCP resource/download abstraction or a separate parsed-data tool. For analysis, parsed records/laps are usually more useful than binary bytes.

## Tool annotations

Initial tools should all use standard read-only annotations, conceptually:

```python
ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    openWorldHint=True,
)
```

Tags could include:

```text
zepp, workouts, health, events, training-load, devices
```

## Naming

Use backend-neutral semantic names where the server name already establishes the Zepp namespace. Prefer `list_workouts` over `zepp_get_run_history_json`.
