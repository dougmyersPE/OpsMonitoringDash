# Project Research Summary

**Project:** ProphetX Market Monitor — v1.2 WebSocket-Primary Status Authority
**Domain:** Internal operations monitoring dashboard — real-time prediction market event lifecycle management
**Researched:** 2026-03-31
**Confidence:** HIGH

## Executive Summary

ProphetX Market Monitor v1.2 promotes the existing WebSocket consumer (`ws_prophetx.py`) from a background data-ingestion service to the authoritative real-time source for `prophetx_status`, demoting the REST polling worker to a reconciliation fallback. The existing stack (FastAPI, Celery/RedBeat, Redis, PostgreSQL, React 19, TanStack Query, shadcn/ui, pysher, structlog) requires no new dependencies — all three v1.2 capabilities (WS diagnostics, status authority model, WS health on dashboard) are achievable through one new DB column (`ws_delivered_at`), new Redis keys, and new API/frontend wiring.

The recommended approach is a four-phase build with a hard gate between Phase 1 and Phase 2. Phase 1 adds structured logging and Redis state keys to confirm that ProphetX actually sends `sport_event` change-type messages on the broadcast channel. STATE.md documents zero such messages observed in production — this is the single greatest risk in v1.2. Building the authority model on an unconfirmed message flow wastes three phases of implementation. Only after confirming `ws:sport_event_count > 0` in production should Phase 2 (the DB schema and poll-demotion logic) proceed.

The primary technical risks are: (1) stale REST poll data overwriting WS-delivered status via a race condition — mitigated by an authority window guard in `poll_prophetx`; (2) pysher's silent dead-connection behavior — mitigated by tracking `last_message_at` separately from the heartbeat TTL; and (3) missed events during token-expiry reconnect windows — mitigated by triggering a one-shot reconciliation poll immediately after reconnect. None of these require new infrastructure; all are targeted code changes to two existing files.

---

## Key Findings

### Recommended Stack

No new dependencies are required for v1.2. The entire milestone is achievable with the currently installed stack. The one schema change — adding `ws_delivered_at TIMESTAMPTZ nullable` to the `events` table — is safe to apply against live data (nullable column, no backfill needed). The authority model uses a single DB column plus a Redis check; no state machine library is warranted for a two-source, two-state problem.

**Core technologies (existing — all applicable to v1.2):**
- **pysher 1.0.7:** WS consumer — already integrated and working in production; maintenance mode but no replacement needed
- **redis-py 5.x:** WS health signal store via `HSET`/`HGETALL`/`INCR` — new `ws:*` key namespace alongside existing `worker:heartbeat:*` keys
- **SQLAlchemy 2.x + Alembic:** `ws_delivered_at` column migration — one `op.add_column`, zero-downtime safe
- **structlog:** WS diagnostic logging — already used in `ws_prophetx.py`; add structured fields at each message decode boundary
- **FastAPI:** New `GET /api/v1/health/ws` endpoint plus modification of `GET /api/v1/health/workers` — no new router required
- **TanStack Query + shadcn/ui:** WS health indicator component — `useQuery` with `refetchInterval: 30_000`, shadcn Badge + Card; no new npm packages

See `.planning/research/STACK.md` for full rationale, implementation patterns, version compatibility notes, and the explicit "what NOT to add" list.

### Expected Features

**Must have — v1.2 Core (P1):**
- `ws_delivered_at` column on `events` table — load-bearing schema foundation; every WS authority decision flows from this timestamp
- `poll_prophetx` authority window guard — skips `prophetx_status` overwrite when `ws_delivered_at` is within 10 min; metadata fields (teams, scheduled_start) still update from REST
- WS health badge on dashboard — `ws_consumer` key added to `GET /health/workers`; `SystemHealth.tsx` gains a "ProphetX WS" badge
- WS reconnect gap detection — on reconnect, log gap duration and trigger `poll_prophetx.apply_async()` immediately
- End-to-end diagnostic verification — confirm structlog entries flow from WS receive → DB write → SSE publish for a known event
- WS subscription confirmation — bind `pusher:subscription_succeeded` handler; log explicitly; timeout if not received within 30s
- `status_match` initialization fix — WS-created events currently skip `compute_status_match()` on insert; pre-existing bug to fix in Phase 1

**Should have — v1.2 Polish (P2, add after core is stable):**
- `ws:connection_state` Redis key with Pusher state detail (connected / reconnecting / disconnected) for richer dashboard display
- Reconciliation run counter in Redis — operational visibility into how often polling fallback is needed
- Source attribution in audit log — `status_source` field in before/after state

**Defer to v1.3+:**
- WS vs. polling update breakdown chart — useful once WS has track record and data has accumulated
- Disconnect duration history / uptime % — requires ring buffer; worth adding after months of data
- Per-sport WS message rate — too granular for current operational needs

**Anti-features — do not build:**
- Full WS message replay / event sourcing buffer — Pusher has no server-side replay; poll reconciliation covers the gap adequately
- Automated WS failover to polling-only mode — oscillation risk; alert operators instead
- Client-side browser WebSocket health monitoring — WS consumer is server-side Python; not applicable

See `.planning/research/FEATURES.md` for full dependency graph, MVP definition, prioritization matrix, and WS-primary authority model technical pattern.

### Architecture Approach

The v1.2 architecture is additive with one behavior change. New components are four Redis keys, one DB column, one FastAPI endpoint, and one frontend component. The one behavior change is `poll_prophetx` gaining an authority window guard that conditionally skips `prophetx_status` writes. ws-consumer and poll-prophetx coordinate exclusively through the `events` DB table — no direct IPC, no new message queue. The SSE stream, mismatch detector, and all other workers are architecturally unchanged; they benefit automatically from faster WS-delivered status updates.

**Major components:**

1. **`ws_prophetx.py` (ws-consumer Docker service)** — sole writer of `ws_delivered_at`; writes four new Redis health keys on each state transition and message receipt; adds structlog fields for end-to-end traceability
2. **`poll_prophetx` (Celery task)** — demoted to reconciliation fallback; gains authority window guard that reads `ws_delivered_at` before overwriting `prophetx_status`; still authoritative for event presence (stale event marking) and all metadata fields
3. **Redis (`ws:*` key namespace)** — health signal store: `ws:connection_state`, `ws:last_message_at` (90s TTL), `ws:last_sport_event_at`, `ws:sport_event_count`; complements existing `worker:heartbeat:*` keys
4. **`GET /api/v1/health/ws` (new endpoint)** — reads `ws:*` Redis keys; returns connection state, last message timestamps, sport event count; no DB queries
5. **`WsHealthIndicator` (new React component)** — added to DashboardPage worker health panel; shows connection state badge plus "last sport_event: X min ago"; uses existing `useQuery` refetch pattern

See `.planning/research/ARCHITECTURE.md` for full data flow diagrams, component boundary analysis, anti-patterns, and confirmed build order.

### Critical Pitfalls

1. **Building authority model before confirming sport_event message flow** — STATE.md records zero `sport_event` messages observed in production. Phase 2 is contingent on a production gate: `ws:sport_event_count > 0` AND `ws:last_sport_event_at` is set. If the gate fails, escalate to ProphetX to verify the broadcast channel carries sport_event change-type messages before writing a single line of Phase 2 code.

2. **Poll worker regresses WS-delivered status (race condition)** — `poll_prophetx` currently overwrites `prophetx_status` unconditionally. Without the authority window guard and lifecycle order check, a stale REST response arriving 30 seconds after a WS `live` delivery would regress the event to `not_started`. This is the riskiest behavior change in v1.2.

3. **Pysher silent dead connection — health shows green but no events arriving** — pysher has no application-level ping; a broken TCP connection may appear "connected" indefinitely while the heartbeat loop continues writing TTL keys. The `ws:last_message_at` 90s TTL acts as a secondary liveness signal and is the primary defense against this failure mode.

4. **Events lost during token-expiry reconnect window** — the `run()` loop proactively disconnects every ~20 minutes for token refresh. Pusher has no message persistence. Transitions missed during the reconnect gap persist until the next scheduled poll (up to 5 min). Mitigation: trigger `poll_prophetx.apply_async()` immediately after every reconnect.

5. **Mismatch alert direction inversion after WS elevation** — `compute_status_match()` was built assuming ProphetX is behind the real world. After WS elevation, ProphetX goes `live` via WS seconds before external sources update, causing false-positive mismatch alerts and potentially spurious `update_event_status` corrections. A 30-second grace period on mismatch alerts when `ws_delivered_at` is recent is required.

See `.planning/research/PITFALLS.md` for full pitfall details, warning signs, recovery strategies, technical debt table, integration gotchas, and the "looks done but isn't" checklist.

---

## Implications for Roadmap

Based on combined research, the v1.2 work divides naturally into four phases with one hard gate. The gate exists because a confirmed production blocker (zero sport_event messages) makes Phases 2 and 3 speculative without Phase 1 evidence.

### Phase 1: WS Diagnostics and Instrumentation
**Rationale:** STATE.md documents zero `sport_event` messages observed in production. This is the single greatest v1.2 risk. Phase 1 installs the sensors needed to confirm or disprove this before any authority logic is built. It also fixes two pre-existing bugs (`status_match` NULL on insert, no subscription confirmation) that must be resolved before the authority model is meaningful.
**Delivers:** Observable WS message flow via Redis health keys (`ws:connection_state`, `ws:last_message_at`, `ws:last_sport_event_at`, `ws:sport_event_count`); `GET /api/v1/health/ws` endpoint; reconciliation poll trigger on reconnect; subscription confirmation logging with 30s timeout; `status_match` initialization fix on WS-created events.
**Addresses:** End-to-end diagnostic verification (P1); gap closure on reconnect (P1); subscription success confirmation.
**Avoids:** Building authority model on unconfirmed message flow (critical pitfall); `status_match` NULL anomalies in mismatch detection.
**Gate condition:** Confirm `ws:sport_event_count > 0` in production before proceeding to Phase 2. If gate fails after 24-48h of live game windows, escalate to ProphetX.

### Phase 2: DB Schema and Status Authority Model
**Rationale:** Requires Phase 1 gate to pass. The `ws_delivered_at` column is the load-bearing change — everything in the authority model flows from it. The poll guard is the highest-risk code change in v1.2 and requires careful testing to ensure it does not create silent status stagnation if WS stops working.
**Delivers:** `ws_delivered_at` column via Alembic migration 007; WS consumer sets `ws_delivered_at` on every event upsert; `poll_prophetx` authority window guard (`WS_AUTHORITY_WINDOW_SECONDS = 600`) prevents stale REST overwrites; lifecycle order guard prevents status regression from either source.
**Uses:** SQLAlchemy `mapped_column` with nullable `DateTime(timezone=True)`, Alembic `op.add_column`, existing `compute_status_match()` function.
**Implements:** WS authority window guard pattern; indirect DB-mediated coordination between ws-consumer and poll worker.
**Avoids:** Poll regression race condition; accidental removal of REST as reconciliation source for new and gap-coverage events.

### Phase 3: WS Health on Dashboard and Mismatch Re-Validation
**Rationale:** Can technically run after Phase 1 (the API endpoint exists). Recommended after Phase 2 so the dashboard reflects the authority model's actual effect, not just connectivity. Mismatch alert direction must be validated here now that WS can deliver status ahead of external sources.
**Delivers:** `WsHealthIndicator` React component on DashboardPage; `GET /health/workers` gains `ws_consumer` key; 30-second grace period in mismatch alert logic to suppress false positives when `ws_delivered_at` is recent; `WS_AUTHORITY_WINDOW_SECONDS` tuned against observed message cadence.
**Uses:** shadcn/ui Badge + Card; TanStack Query `useQuery` with `refetchInterval: 30_000`; existing `GET /api/v1/health/ws` from Phase 1.
**Implements:** WS connection state detail display; mismatch direction re-validation.
**Avoids:** False-positive mismatch alerts during WS authority elevation; binary up/down health indicator masking message silence.

### Phase 4: Tech Debt
**Rationale:** No dependencies on any other v1.2 phase. Can run in parallel with Phase 1 (the observation window is 24-48h; tech debt can fill the wait) or between any two phases.
**Delivers:** `SportsApiClient` aligned with `BaseAPIClient` inheritance; Sports API Redis reads replaced with `MGET` batch; any additional cleanup identified during Phase 1-3 implementation.
**Avoids:** Performance trap from sequential Redis reads accumulating as event volume grows.

### Phase Ordering Rationale

- Phase 1 is unconditionally first: the production gate (zero sport_event messages confirmed in STATE.md) makes all subsequent phases speculative without it. The ARCHITECTURE.md anti-pattern "Building Authority Logic Before Confirming WS Message Flow" applies directly.
- Phase 2 is gated on Phase 1 passing: the authority window guard is meaningless if `ws_delivered_at` is never set because sport_event messages never arrive.
- Phase 3 is recommended after Phase 2: the health indicator is more meaningful when the authority model is active, and the mismatch grace period requires `ws_delivered_at` to exist (Phase 2 deliverable).
- Phase 4 is fully independent: schedule opportunistically or use the Phase 1 observation window as the deployment slot.

### Research Flags

Needs deeper research or production validation during planning:

- **Phase 1 (gate validation):** If `ws:sport_event_count` remains zero after 24-48h covering live game windows, requires a ProphetX channel investigation. Confirm channel name, subscription auth endpoint, and whether sport_event messages are sent on the current broadcast channel vs. a different private channel. This is an external-dependency investigation, not a code problem.
- **Phase 2 (`WS_AUTHORITY_WINDOW_SECONDS` tuning):** The suggested default of 10 minutes (2x the poll interval) must be validated against observed WS message cadence during real game windows. Should be an environment variable or `SystemConfig` table entry, not a hardcoded constant, to allow tuning without deployment.

Standard patterns (no additional research needed):

- **Phase 2 (Alembic migration):** `op.add_column` with nullable column is fully documented; zero-downtime safe against live data; confirmed safe default (NULL correctly interpreted as "never received from WS").
- **Phase 3 (React component):** TanStack Query polling + shadcn/ui Badge is established project pattern with no new libraries or patterns.
- **Phase 4 (Tech debt):** Standard SQLAlchemy inheritance refactor and Redis `MGET` batch optimization; well-documented patterns with no external dependencies.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | No new dependencies; all packages confirmed installed and working in production. Pysher bindable events confirmed from source code inspection and Pusher protocol docs. |
| Features | HIGH | Codebase fully inspected; all integration points verified against live code. Feature scope grounded in actual gaps in the production system, not assumptions. |
| Architecture | HIGH | All component boundaries, data flows, and integration patterns verified against deployed code. Race condition analysis confirmed against actual concurrency model (single-threaded ws-consumer + Celery worker). |
| Pitfalls | HIGH | Pitfalls derived from direct code inspection of the actual files that will be changed; Pusher/pysher behavior confirmed from official docs and library source inspection. |

**Overall confidence:** HIGH

### Gaps to Address

- **ProphetX sport_event message delivery (production unconfirmed):** The single unresolved gap. STATE.md documents zero `sport_event` change-type messages observed on the broadcast channel. All of Phase 2 depends on this being confirmed in production after Phase 1 is deployed. If messages never appear after 24-48h covering live game windows, the entire authority model concept requires re-evaluation of channel configuration, subscription parameters, or ProphetX account-level permissions.

- **Exact `WS_AUTHORITY_WINDOW_SECONDS` value:** Research suggests 10 minutes (2x the poll interval). The correct value depends on observed ProphetX WS message cadence under real game-time conditions. This parameter should be tunable without code changes. Validate and adjust after Phase 1 observation window.

- **Mismatch grace period duration:** PITFALLS.md suggests 30 seconds to suppress false-positive alerts when WS delivers status ahead of external sources. The correct value depends on how quickly SDIO, Odds API, and ESPN propagate live game transitions. Validate during Phase 3 against real game-time data before hardcoding.

---

## Sources

### Primary (HIGH confidence)
- Direct codebase inspection (2026-03-31): `ws_prophetx.py`, `poll_prophetx.py`, `update_event_status.py`, `mismatch_detector.py`, `health.py`, `stream.py`, `models/event.py`, `celery_app.py`, `docker-compose.yml` — all integration points and current behavior verified
- pysher 1.0.7 source code (locally installed) — bindable event names and state values confirmed from `python3 -c "import inspect,pysher; print(inspect.getsource(pysher.connection))"`
- Pusher Channels WebSocket Protocol documentation — `pusher:connection_established`, `pusher:subscription_succeeded`, `pusher:error`, `pusher:ping`/`pusher:pong` confirmed
- Pusher connection states documentation — six states (initialized, connecting, connected, unavailable, failed, disconnected) confirmed
- Pusher missed-events documentation — confirmed no server-side message persistence; clients must implement own gap recovery

### Secondary (MEDIUM confidence)
- Pusher Channels missed messages documentation (`docs.bird.com`) — reconnect gap behavior confirmed; specific timing details may vary
- WebSocket reconnection guide (`websocket.org`) — token expiry plus reconnect window patterns; general WS reconnection strategies
- WebSocket connection health monitoring patterns (`oneuptime.com/blog`) — dashboard metrics patterns for WS health display

### Tertiary (informational)
- pysher PyPI / GitHub — maintenance mode status confirmed; long-term support posture noted (not a current concern; pysher is working in production today)

---
*Research completed: 2026-03-31*
*Ready for roadmap: yes*
