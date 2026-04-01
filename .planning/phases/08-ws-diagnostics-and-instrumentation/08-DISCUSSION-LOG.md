# Phase 8: WS Diagnostics and Instrumentation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-31
**Phase:** 08-ws-diagnostics-and-instrumentation
**Areas discussed:** Reconnect reconciliation

---

## Reconnect Reconciliation

### Q1: When should reconnect trigger a poll_prophetx reconciliation run?

| Option | Description | Selected |
|--------|-------------|----------|
| Any reconnect (Recommended) | Fire reconciliation after every reconnect — both error recovery AND token refresh. Simple, no missed gaps. poll_prophetx is cheap. | ✓ |
| Error reconnects only | Only fire after an unclean disconnect (exception path). Skip on normal token-refresh cycles. | |
| Gap-aware reconnects | Track disconnect duration; only reconcile if gap exceeds a threshold (e.g., 60s). | |

**User's choice:** Any reconnect (Recommended)
**Notes:** None

### Q2: How should the WS consumer trigger poll_prophetx?

| Option | Description | Selected |
|--------|-------------|----------|
| Celery send_task (Recommended) | Import celery_app and call celery_app.send_task('poll_prophetx') — enqueues via Redis broker without needing the task module imported. | ✓ |
| Redis pub/sub signal | Publish a 'reconcile' message to a Redis channel; a listener in the Celery worker picks it up. More decoupled but adds complexity. | |

**User's choice:** Celery send_task (Recommended)
**Notes:** None

### Q3: Should the reconciliation fire immediately on reconnect, or after a short delay?

| Option | Description | Selected |
|--------|-------------|----------|
| Immediate (Recommended) | Fire poll_prophetx as soon as _connect_and_run() starts a new connection. The poll task runs independently via Celery. | ✓ |
| Short delay (5-10s) | Wait a few seconds after reconnect before firing, in case the connection drops again immediately (flapping). | |

**User's choice:** Immediate (Recommended)
**Notes:** None

### Q4: Should the reconciliation run be logged/tagged differently from regular scheduled runs?

| Option | Description | Selected |
|--------|-------------|----------|
| Tag with trigger source (Recommended) | Pass a kwarg like trigger='ws_reconnect' so poll_prophetx logs show whether it was a scheduled run or a reconnect-triggered run. | ✓ |
| No special tagging | Just fire the same task — it's the same work either way. Keep it simple. | |

**User's choice:** Tag with trigger source (Recommended)
**Notes:** Useful for debugging during Phase 8 observation window

---

## Claude's Discretion

- Redis health key design (TTLs, formats, update frequency)
- WSREL-02 fix (status_match on new events) — straightforward bug fix
- Production gate observation workflow

## Deferred Ideas

None — discussion stayed within phase scope
