# Phase 10: WS Health Dashboard - Context

**Gathered:** 2026-04-01
**Status:** Ready for planning

<domain>
## Phase Boundary

Surface ProphetX WebSocket connection health on the dashboard. Extend the `/health/workers` endpoint to include WS connection status from Redis diagnostic keys (set up in Phase 8). Display a WS health badge alongside existing poll worker badges. Show Pusher connection state detail (connected/connecting/reconnecting/unavailable) with last state transition timestamp via tooltip.

</domain>

<decisions>
## Implementation Decisions

### Badge Presentation (WSHLT-02)
- **D-01:** WS badge sits in the same row as existing poll worker badges, using identical pill styling (green dot + label). No visual separation — it's a peer badge.
- **D-02:** Green/red binary only — `connected` = green, everything else (connecting/reconnecting/unavailable/missing) = red. Matches existing worker badge behavior exactly.

### State Detail Display (WSHLT-03)
- **D-03:** Pusher state detail shown via native HTML `title` attribute tooltip on the WS badge. Pattern: `"ProphetX WS: {state}\nSince: {relative_time}"`. Consistent with existing badge `title` attributes.
- **D-04:** No styled tooltip component — use the same native title approach already on worker badges. Zero new dependencies.

### Claude's Discretion
- Health endpoint response shape for `ws_prophetx` — can be a richer object (state + timestamps) even though frontend only needs boolean + state + transition time. The endpoint already returns booleans for poll workers; Claude decides whether to keep WS as boolean and add a separate field, or return a nested object.
- How to compute "since" relative time on the frontend — existing patterns may already have a utility or it can be computed inline.
- Whether to read `ws:sport_event_count` and `ws:last_message_at` in the health endpoint even though they aren't displayed (future-proofing vs YAGNI). Claude decides.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Backend — Health Endpoint
- `backend/app/api/v1/health.py` — Current `/health/workers` endpoint; needs WS keys added to Redis mget call
- `backend/app/db/redis.py` — `get_redis_client()` async Redis connection

### Frontend — SystemHealth Component
- `frontend/src/components/SystemHealth.tsx` — Current worker badge component; WS badge added here
- `frontend/src/components/Layout.tsx` — Where SystemHealth is rendered

### Redis WS Diagnostic Keys (from Phase 8)
- `backend/app/workers/ws_prophetx.py` — WS consumer that writes `ws:connection_state`, `ws:last_message_at`, `ws:last_sport_event_at`, `ws:sport_event_count` to Redis

### Requirements
- `.planning/REQUIREMENTS.md` §WS Health Dashboard — WSHLT-01, WSHLT-02, WSHLT-03

### Phase 8 Context (predecessor)
- `.planning/phases/08-ws-diagnostics-and-instrumentation/08-CONTEXT.md` — Redis key design decisions (120s TTL on connection keys, no TTL on counters)
- `.planning/phases/08-ws-diagnostics-and-instrumentation/08-01-SUMMARY.md` — What was built in Phase 8

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `SystemHealth.tsx` — Full badge component with react-query polling (30s), `cn()` utility for conditional classes, `WORKERS` array pattern for adding new badges
- `/health/workers` endpoint — Redis `mget` pattern for batch key reads; straightforward to add `ws:connection_state` key
- `get_redis_client()` — Async Redis client used throughout API layer

### Established Patterns
- Worker badge: `WORKERS` array defines `{key, label}` pairs — adding WS is one array entry + type extension
- Health endpoint: Returns flat `{worker_name: boolean}` dict — WS data may need a slightly richer shape for state detail
- `title` attribute on badge `<span>` elements: `${label}: ${active ? "healthy" : "offline"}` — extend for WS with state + timestamp
- React Query: `refetchInterval: 30_000` on worker health — WS badge inherits same 30s refresh cycle

### Integration Points
- `WorkerHealth` TypeScript interface in `SystemHealth.tsx` — extend with `ws_prophetx` field
- `WORKERS` array in `SystemHealth.tsx` — add entry for WS badge
- `/health/workers` endpoint — add `ws:connection_state` (and optionally `ws:last_message_at`) to Redis reads
- Badge rendering logic — WS badge needs custom title text (state + time) vs simple "healthy/offline"

</code_context>

<specifics>
## Specific Ideas

- ROADMAP success criteria #4: "WS health badge reflects current state within 30 seconds of a connection change" — already satisfied by existing 30s react-query polling + 120s Redis TTL on `ws:connection_state`
- Existing badge `title` text is `"${label}: ${active ? 'healthy' : 'offline'}"` — WS badge extends this to include Pusher state name and relative transition time

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 10-ws-health-dashboard*
*Context gathered: 2026-04-01*
