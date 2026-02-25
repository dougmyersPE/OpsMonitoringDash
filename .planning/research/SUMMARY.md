# Project Research Summary

**Project:** ProphetX Market Monitor
**Domain:** Real-time operations monitoring dashboard — prediction market / sports event lifecycle management
**Researched:** 2026-02-24
**Confidence:** MEDIUM-HIGH (established patterns; ProphetX-specific API behavior unverified)

## Executive Summary

ProphetX Market Monitor is a real-time internal operations dashboard for monitoring prediction market events and liquidity. The system follows a well-established NOC/SOC dashboard architecture: a Python/FastAPI backend with Celery/Redis background workers poll two external APIs (ProphetX and SportsDataIO) every 30 seconds, detect status mismatches and low-liquidity conditions, take automated corrective actions, and push updates to the React dashboard via Server-Sent Events. The core challenge is not technical novelty — it's reliability. Every piece of the system (polling, matching, alerting, auto-correction) operates in a loop with financial consequences if it misfires, so defensive patterns (idempotency, deduplication, distributed locks, confidence-gated automation) are non-negotiable from day one.

The highest-risk element of the entire build is the event ID matching layer. ProphetX and SportsDataIO use completely different identifiers for the same real-world game, and the fuzzy matching logic (sport + normalized team names + scheduled start time) is the single bottleneck that everything else depends on. Without a working matcher producing high-confidence results, no status comparisons are valid and no automated actions should fire. This means the matching layer must be built, validated against real API data, and stress-tested for edge cases (double-headers, playoff rematches, team name variants) before the worker engine is considered complete. Budget significant time here.

The recommended rollout strategy — built into the architecture from the start — is alert-only mode: a single config flag (`auto_updates_enabled`) that allows the system to detect and alert on mismatches without writing any changes to ProphetX. The system should run in this mode for at least 48 hours before enabling automated status updates. This requires alert deduplication (a Redis TTL-based per-condition rate limiter) to be in place before Slack goes live; otherwise a single stuck mismatch generates 120 Slack alerts per hour and operators will immediately distrust the channel. These two requirements (alert-only mode flag, deduplication) are v1 blockers for production use even though they read like polish features.

## Key Findings

### Recommended Stack

The backend stack is FastAPI (0.115.x) + Celery (5.4.x) + Redis (7.x) + PostgreSQL (16.x) on Python 3.12. This is the established choice for async Python services that need periodic background work. FastAPI provides native SSE support via `StreamingResponse`; Celery provides distributed task scheduling with retry queues; Redis serves triple duty as Celery broker, application state cache, and SSE pub/sub bus. The frontend is React 18 + TypeScript + Vite + TanStack Query + Tailwind CSS + shadcn/ui. SSE (not WebSockets) is the right choice for unidirectional server-to-client push in this context. Version compatibility is critical: FastAPI 0.100+ requires Pydantic v2; TanStack Query v5 requires React 18; celery-redbeat 2.x requires Celery 5; Celery 5.4+ is required for Python 3.12 support.

**Core technologies:**
- FastAPI 0.115.x: REST API + SSE backend — async-native, Pydantic v2 integrated, first-class SSE via `StreamingResponse`
- Celery 5.4.x + celery-redbeat 2.x: Polling engine + Beat scheduler — industry standard for periodic tasks; redbeat required to prevent duplicate tasks on container restart
- Redis 7.x: Broker + cache + pub/sub — single service covering three roles; use separate databases (db=0, db=1, db=2) to isolate concerns
- PostgreSQL 16.x + SQLAlchemy 2.x async + asyncpg: Primary store — use async engine throughout; never `psycopg2` which blocks the event loop
- React 18 + TanStack Query 5.x: Dashboard UI — SSE triggers `queryClient.invalidateQueries` rather than patching local state
- httpx + tenacity: External API calls with exponential backoff retry across ProphetX, SportsDataIO, and all clients
- uv + Ruff + mypy: Python toolchain — `uv` replaces pip/poetry; Ruff replaces Black+flake8; all configured in `pyproject.toml`

See `.planning/research/STACK.md` for full library list and version compatibility matrix.

### Expected Features

The system has a well-defined feature set from a detailed PRD. Table stakes are numerous because this is a financially consequential ops tool — a basic dashboard with no auth, no audit log, and no alert deduplication would be a liability, not a product.

**Must have (table stakes):**
- Event ID matching layer (sport + fuzzy team names + start time window) — system is non-functional without this
- Celery polling workers (poll_prophetx + poll_sports_data on 30-second schedule) — the monitoring engine
- Automated status sync (Upcoming → Live → Ended) with idempotent ProphetX writes
- Postponed/cancelled event detection with dashboard flagging and alerts
- Liquidity threshold monitoring with configurable per-market thresholds
- Real-time dashboard: Events Table + Markets Table with mismatch/liquidity highlighting via SSE
- Slack webhook alerting with alert deduplication (1 alert per event per condition per 5–15 minutes)
- In-app notification center (bell + panel, read/unread, click-to-navigate)
- Audit log (append-only PostgreSQL, no UPDATE/DELETE, before/after state in JSONB)
- JWT authentication + RBAC (Admin / Operator / Read-Only) with server-side enforcement
- Admin config panel (liquidity thresholds, polling interval, Slack webhook URL)
- Alert-only mode flag (`auto_updates_enabled`) — gates all ProphetX write actions
- Worker health indicator — operators must know if polling has stopped
- "Action Failed" state with retry CTA on dashboard

**Should have (operational advantage):**
- Manual event mapping correction UI — when auto-matching produces wrong results, admins need a UI fix path
- Audit log search/filter UI (date range, actor, event, action type)
- Supplementary data source fallback (The Odds API or ESPN) for SportsDataIO coverage gaps
- Slack digest for bulk status changes (NFL Sunday batching)
- Notification acknowledgement (is_acknowledged, acknowledged_by, acknowledged_at)
- ProphetX API circuit breaker (open/half-open/closed states)

**Defer to v2+:**
- Automated liquidity top-up — blocked until ProphetX top-up API mechanics are confirmed and system has 2+ stable weeks
- Historical analytics / trend charts — significant scope; Slack + audit log covers v1 operational needs
- Email/SMS alerting — Slack covers the immediate team; email digest is a future reporting feature
- Per-user notification preferences — premature for a small team; add when team grows beyond 5 operators
- Alert escalation chains (PagerDuty-style) — add only if SLA requirements demand it

See `.planning/research/FEATURES.md` for full prioritization matrix and dependency graph.

### Architecture Approach

The system follows a 4-layer architecture: External Data Sources → Background Worker Layer (Celery Beat + Poll Workers + Action Workers) → Data Layer (PostgreSQL + Redis) → API/Delivery Layer (FastAPI) → Frontend (React SPA). Workers and the API communicate exclusively via Redis pub/sub — no direct imports between them. The services/ layer (mismatch detector, liquidity monitor, event matcher) is framework-agnostic Python business logic callable by both workers and API handlers. External API calls are isolated in a clients/ layer so ProphetX/SportsDataIO changes only touch one file.

**Major components:**
1. Celery Beat (redbeat) — schedules poll_prophetx and poll_sports_data on 30-second intervals; must run as its own Docker container, never embedded in FastAPI
2. Poll Workers — fetch external data, run mismatch/liquidity detection, enqueue action tasks to a separate action_queue; never call external APIs from inside alerting code
3. Action Workers — execute ProphetX status updates (idempotent, with distributed lock and intent-first DB write pattern), send Slack alerts (with deduplication), write audit log, publish to Redis pub/sub
4. Event Matching Layer (event_matcher.py + event_id_mappings table) — run once per new event discovery; cache result in Redis for O(1) poll-cycle lookup; never re-run on every cycle
5. FastAPI Backend — REST endpoints + SSE /stream endpoint (subscribes to Redis pub/sub channels); JWT/RBAC enforcement on all write endpoints
6. React Dashboard — EventSource() consumes SSE stream; TanStack Query handles REST data; SSE events trigger cache invalidation rather than local state patching

See `.planning/research/ARCHITECTURE.md` for component boundary rules, full data flow diagrams, and project directory structure.

### Critical Pitfalls

1. **Duplicate automated actions (double-fire)** — Two workers detect the same mismatch in overlapping cycles and both enqueue `update_event_status`, causing duplicate ProphetX API calls and false "Action Failed" alerts. Prevention: Redis distributed lock (`SET NX EX 60`) keyed on `lock:status_update:{event_id}` before enqueuing any action task. Must be built into Phase 2 from day one.

2. **Fuzzy matching false positives (wrong game updated)** — The event matcher links a ProphetX event to the wrong SportsDataIO game; the system confidently auto-updates the wrong event. Prevention: require all three criteria simultaneously (exact sport match, ≥0.85 fuzzy team score, start time within ±15 minutes); gate all auto-actions behind a ≥0.90 composite confidence threshold; flag anything below for manual review. Never auto-act on low-confidence matches.

3. **Alert storms causing operator blindness** — Every 30-second cycle re-detects the same unresolved mismatch and fires a new Slack alert. After 10 minutes: 20 identical alerts, operators stop reading Slack, real new alerts are missed. Prevention: Redis TTL key per `alert_sent:{event_id}:{condition_type}` with 5-minute suppression window; implement "still unresolved" re-alert context after window expires. This is a v1 production blocker, not polish.

4. **SSE silent stale connection** — Network hiccup or Nginx idle timeout (default 60s) kills the SSE connection; the dashboard keeps displaying frozen data with no warning. Prevention: server-side heartbeat comment every 15 seconds (keeps connection alive, makes drops detectable); visible "Connection lost — reconnecting..." banner in React when EventSource enters CONNECTING state; Nginx `proxy_read_timeout 3600s; proxy_buffering off;` for the SSE location block.

5. **Automated actions without idempotency** — Network timeout after ProphetX API success causes Celery to retry; the second call double-applies the action. Prevention: write-intent pattern (set status to `update_pending` in DB before calling ProphetX; verify current ProphetX state at start of any retry — if already correct, mark complete without re-calling). Non-retrofittable; must be the default pattern for all action tasks from Phase 2.

6. **ProphetX status enum assumptions** — Comparison logic built against guessed values (`"upcoming"`, `"live"`) never matches actual API values (`"SCHEDULED"`, `"IN_PROGRESS"`); system runs clean but never detects mismatches. Prevention: log every raw status value from ProphetX on the first integration test; build the Python enum from observed data, not documentation; add a `WARNING: unknown_prophetx_status` fallback for new values post-launch.

See `.planning/research/PITFALLS.md` for full pitfall details, warning signs, recovery strategies, and a phase-to-pitfall mapping.

## Implications for Roadmap

Based on the combined research, the architecture's own dependency graph strongly suggests a 5-phase structure. Phases are not discretionary — each layer depends on the one before it. The event ID matching layer is the critical path through Phase 2 and must be treated as a validation gate before Phase 3 begins.

### Phase 1: Foundation and Infrastructure

**Rationale:** Every other component depends on the database schema, environment configuration, Redis setup, and API client layer being in place. Auth also belongs here — it must be present before any write-capable endpoint is exposed, even in development.
**Delivers:** Running Docker Compose skeleton (postgres, redis, backend, frontend, celery, nginx), SQLAlchemy models and Alembic migrations for all 6 entities (Event, Market, AuditLog, User, Notification, Config), JWT auth system, ProphetX and SportsDataIO API client classes with retry/backoff, pydantic-settings config, Redis database separation (db=0/1/2), redbeat configuration, Redis maxmemory policy.
**Addresses features:** JWT authentication, RBAC foundation, admin config model
**Avoids pitfalls:** Celery Beat clock drift (configure redbeat here, not later), Redis memory exhaustion (set maxmemory in docker-compose.yml now), ProphetX enum assumptions (client logs raw responses from first call), API key exposure (pydantic-settings from env, never in code)
**Research flag:** Standard patterns — no additional research needed; these are well-documented FastAPI/Celery/PostgreSQL setup patterns.

### Phase 2: Monitoring Engine (Background Workers)

**Rationale:** The worker engine is the core value of the system. It must be built before the API layer can serve meaningful data and before the dashboard has anything to display. The event ID matching layer is the highest-risk dependency and must be built and validated against real ProphetX + SportsDataIO responses before poll worker logic is finalized.
**Delivers:** Event ID matching layer (event_matcher.py, event_id_mappings table, rapidfuzz scoring, confidence gating), mismatch detector service, liquidity monitor service, poll_prophetx and poll_sports_data Celery tasks, update_event_status action task (with distributed lock + idempotent write-intent pattern), Celery queue separation (poll_queue / action_queue), audit writer service.
**Uses:** ProphetX client + SportsDataIO client from Phase 1, Redis lock pattern, SQLAlchemy async sessions
**Implements:** Background Worker Layer from architecture diagram
**Critical gate:** After Phase 2 is complete, run the matching layer against live ProphetX and SportsDataIO data for 24–48 hours. Review match confidence scores and confirm the comparisons are detecting real mismatches before building the frontend on top of this output.
**Avoids pitfalls:** Double-fire duplicates (distributed lock built in here), idempotency failures (write-intent pattern is default from start), wrong-event auto-updates (confidence gating built into matcher), ProphetX enum assumptions (validate raw responses before writing comparison logic)
**Research flag:** Needs research during planning — ProphetX API rate limits, pagination behavior, exact status enum values, and SportsDataIO sport endpoint coverage must be confirmed against actual API documentation before this phase begins.

### Phase 3: API Layer and Real-Time Delivery

**Rationale:** REST endpoints and the SSE stream can only serve meaningful data after Phase 2 workers have populated the database. The SSE endpoint depends on Phase 2 workers publishing to Redis pub/sub channels.
**Delivers:** All REST endpoints (/events, /markets, /audit-log, /notifications, /config), SSE /stream endpoint with heartbeat and event ID support, manual sync trigger (POST /events/{id}/sync-status), RBAC enforcement on all write endpoints, SSE stale-connection banner in React, Nginx SSE configuration (proxy_buffering off, proxy_read_timeout 3600s).
**Implements:** API/Delivery Layer from architecture diagram; FastAPI → Redis pub/sub subscription pattern
**Avoids pitfalls:** SSE silent stale connection (heartbeat + stale banner built in here, not deferred to polish phase), JWT token logging in Nginx (short-lived SSE token exchange or cookie auth for SSE endpoint)
**Research flag:** Standard patterns — FastAPI SSE and TanStack Query patterns are well-documented; no additional research needed.

### Phase 4: React Dashboard and Alerting

**Rationale:** The dashboard is the operator-facing surface; it can only be built meaningfully once the API layer exists and serves real data. Alerting (Slack + in-app notifications) belongs in this phase because alert deduplication must be in place before Slack goes live in production.
**Delivers:** Events Table with status mismatch highlighting, Markets Table with liquidity threshold view, useSSE hook (EventSource + TanStack Query cache invalidation), notification bell + notification center, Slack webhook client + send_alerts worker with Redis TTL-based deduplication, alert-only mode flag enforcement (gates all ProphetX writes), admin config panel (thresholds, polling interval, Slack URL), worker health indicator, "Action Failed" badge with retry CTA.
**Implements:** Frontend Layer from architecture diagram; complete alert delivery pipeline
**Avoids pitfalls:** Alert storms (deduplication built in before Slack goes live, not post-launch), alert-only mode required for rollout plan (config flag built in Phase 4, not after go-live)
**Research flag:** Alert deduplication implementation is well-documented (Redis TTL pattern); Slack Block Kit formatting is well-documented. Standard patterns — no additional research needed.

### Phase 5: Polish, Hardening, and Production Deployment

**Rationale:** Hardening tasks span all layers and are best done after the full system is functional end-to-end so the blast radius of each change is known.
**Delivers:** Full Nginx + SSL (Certbot) configuration, production Docker Compose hardening (health checks, restart policies, named volumes, secret management), database indexes on hot query paths (prophetx_event_id, status_match, audit_log.timestamp), error/empty/loading states in all UI components, RBAC server-side enforcement audit (verify DB-level INSERT-only on audit_log), "looks done but isn't" checklist verification for all 8 critical behaviors from PITFALLS.md, supplementary data source fallback (The Odds API / ESPN), audit log search/filter UI.
**Avoids pitfalls:** Redis memory exhaustion (verify with `redis-cli info memory` after 48 hours), SSE Nginx timeout (proxy_read_timeout set here), audit log mutability (PostgreSQL GRANT enforcement verified), RBAC bypass (server-side role check audit)
**Research flag:** Nginx SSE configuration and Let's Encrypt Certbot patterns are well-documented. Standard patterns.

### Phase Ordering Rationale

- **Infrastructure before workers:** SQLAlchemy models, Redis configuration, and API clients must exist before any worker can run. This is a hard dependency, not a preference.
- **Workers before API:** The REST endpoints for /events and /markets are only meaningful once workers have polled and populated the database. The SSE stream requires workers to be publishing to Redis pub/sub channels.
- **API before dashboard:** The React dashboard needs real endpoints to develop against. Building it against mocked data delays discovery of API shape mismatches.
- **Alert deduplication in Phase 4 not Phase 5:** The research is emphatic that deduplication is a correctness requirement, not a polish feature. Slack must not go live without it.
- **Event matching as Phase 2 gate:** The matching layer is placed at the start of Phase 2 and marked as a validation gate specifically because everything downstream (mismatch detection, auto-updates, dashboard data) is invalid if matching is broken.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 2:** ProphetX API — rate limits per minute, pagination behavior, exact status enum values (SCHEDULED vs. upcoming vs. IN_PROGRESS), error codes for invalid status transitions (409? 422?). SportsDataIO — which sport endpoints are covered by the subscription, exact terminal status values beyond "Final" (F/OT, F/SO, Postponed, Canceled, Suspended), daily request limits per sport. These must be confirmed against actual API documentation before Phase 2 work begins. Plan a spike day to log raw API responses before writing any comparison logic.

Phases with standard patterns (skip research-phase):
- **Phase 1:** FastAPI + Celery + PostgreSQL + Redis setup — extremely well-documented, stable ecosystem
- **Phase 3:** FastAPI SSE + TanStack Query + Redis pub/sub — established patterns with working code examples in STACK.md and ARCHITECTURE.md
- **Phase 4:** Slack Block Kit + Redis TTL deduplication — well-documented
- **Phase 5:** Nginx SSE config + Certbot + Docker hardening — standard production patterns

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM | Core technology choices are HIGH confidence (FastAPI, Celery, React ecosystem are mature and well-documented). Version numbers could not be live-verified (web search unavailable) — recommend running `pip index versions fastapi celery sqlalchemy` and checking npm registry before creating lockfiles. |
| Features | HIGH | Domain is well-understood; PRD is detailed and specific; NOC/SOC dashboard and trading ops patterns are established. Feature categorization (table stakes vs. differentiators vs. anti-features) is based on solid domain knowledge. |
| Architecture | HIGH | Celery/FastAPI/Redis/SSE patterns are well-established and stable. The 4-layer architecture, component boundary rules, and data flow diagrams are based on documented, production-proven patterns. |
| Pitfalls | HIGH for infrastructure pitfalls; MEDIUM for ProphetX-specific behavior | Celery/Redis/SSE failure modes are well-documented and stable. ProphetX-specific behavior (rate limits, status enum values, idempotency guarantees on their PATCH endpoint) is MEDIUM confidence — cannot be verified without access to ProphetX API documentation. |

**Overall confidence:** MEDIUM-HIGH

### Gaps to Address

- **ProphetX API documentation access:** Rate limits, exact status enum values, PATCH idempotency behavior, and error codes for invalid status transitions must be confirmed against actual ProphetX API documentation before Phase 2 begins. This is the single most important validation step in the entire project.
- **SportsDataIO subscription coverage:** The subscription tier determines which sports endpoints are available. The polling logic and event matching must be scoped to confirmed coverage. Attempting to poll uncovered sports returns 403 silently.
- **SportsDataIO terminal status values:** The research identified that `Final` is not the only terminal state (F/OT, F/SO, Postponed, Canceled, Suspended). All terminal and in-progress state values for each covered sport must be mapped before the comparison logic can be trusted.
- **Package version pinning:** Stack research was conducted without live web access. All version recommendations are based on training data through August 2025. Confirm that FastAPI 0.115.x, Celery 5.4.x, celery-redbeat 2.x, and TanStack Query 5.x are current stable releases before creating lockfiles.
- **Team name alias coverage:** The event matching layer requires a `TEAM_NAME_ALIASES` dictionary that maps ProphetX team name variants to canonical forms. This must be populated from actual ProphetX API responses — the initial set cannot be pre-defined without seeing real data.

## Sources

### Primary (HIGH confidence)
- `.planning/PROJECT.md` — project constraints, key decisions, deployment target
- `docs/PRD.md` (ProphetX Market Monitor, v1.0, 2026-02-24) — primary feature specification
- FastAPI official documentation — SSE via `sse-starlette`, dependency injection, async SQLAlchemy patterns
- SQLAlchemy 2.0 documentation — async engine, `async_sessionmaker`, `selectinload` patterns
- Celery 5.x documentation — periodic tasks, task routing, retry policies, `acks_late` behavior
- celery-redbeat documentation — Redis-backed Beat scheduler, container restart safety

### Secondary (MEDIUM confidence)
- Redis pub/sub pattern for SSE fan-out — established industry pattern; training data through August 2025
- rapidfuzz library for fuzzy string matching — commonly used for entity resolution in Python data pipelines
- NOC/SOC dashboard patterns — domain analogy; features validated against PagerDuty, Grafana, OpsGenie feature sets
- Trading operations tooling — domain analogy; RBAC, audit log, and alert deduplication requirements confirmed against trading ops patterns

### Tertiary (requires live validation)
- ProphetX API behavior (rate limits, status enums, idempotency) — MEDIUM confidence; must be verified against actual API documentation and live testing
- SportsDataIO subscription coverage and terminal status values — MEDIUM confidence; must be confirmed against actual subscription tier
- Specific library version numbers — requires live npm/PyPI verification before lockfile creation

---
*Research completed: 2026-02-24*
*Ready for roadmap: yes*
