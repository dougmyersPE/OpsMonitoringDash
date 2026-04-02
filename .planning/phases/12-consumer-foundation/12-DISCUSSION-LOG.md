# Phase 12: Consumer Foundation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-02
**Phase:** 12-consumer-foundation
**Areas discussed:** Queue lifecycle scope, Endpoint path resolution, Unknown status handling

---

## Queue Lifecycle Scope

| Option | Description | Selected |
|--------|-------------|----------|
| Self-managing only (Recommended) | Consumer starts queue on boot, stops on SIGTERM. No REST endpoints. Operators restart via docker compose restart. Simpler, matches ws-consumer pattern exactly. | ✓ |
| Add REST endpoints | POST /api/v1/opticodds/queue/start, /stop, GET /status. Lets operators control the queue from the API without SSH. More operational flexibility but adds API routes + auth. | |
| You decide | Claude picks based on existing patterns and phase scope. | |

**User's choice:** Self-managing only (Recommended)
**Notes:** Matches ws-consumer precedent. REST endpoints noted as deferred idea.

---

## Endpoint Path Resolution

| Option | Description | Selected |
|--------|-------------|----------|
| Configurable env var (Recommended) | OPTICODDS_BASE_URL env var defaults to best guess (/v3/copilot/results/queue/start per Oct 2025 changelog). Easy to fix without code change if wrong. | ✓ |
| Verify first, then hardcode | Test against live creds before planning. Hardcode the confirmed path. Requires manual verification step before Phase 12 execution. | |
| Try both with fallback | Client tries /v3/copilot/ path first, falls back to /fixtures/ on 404. Auto-discovers the right one but adds complexity. | |

**User's choice:** Configurable env var (Recommended)
**Notes:** Default to /v3/copilot/ path. No blocking verification step required before implementation.

---

## Unknown Status Handling

| Option | Description | Selected |
|--------|-------------|----------|
| Log WARNING + Slack alert (Recommended) | Unknown status logged at WARNING level AND triggers a Slack alert so operators investigate. Consistent with how walkover/retired/suspended already trigger alerts (TNNS-03). Operators see it, no silent data loss. | ✓ |
| Log WARNING only | Unknown status logged at WARNING level but no Slack alert. Keeps Slack noise down. Operators would need to check logs to discover new statuses. | |
| Store raw + log WARNING | Write the unknown status string verbatim to opticodds_status column AND log WARNING. No Slack alert. At least the data is captured even if unmapped. | |

**User's choice:** Log WARNING + Slack alert (Recommended)
**Notes:** None

### Follow-up: DB Write for Unknown Statuses

| Option | Description | Selected |
|--------|-------------|----------|
| Write raw value to DB | Store the unknown status string verbatim in opticodds_status. Data is preserved; operators can see it in the dashboard. Avoids losing information. | ✓ |
| Skip DB write, alert only | Don't write unrecognized values to the column. Only known statuses get stored. Cleaner data but potential information loss. | |

**User's choice:** Write raw value to DB
**Notes:** Full approach: write raw + log WARNING + Slack alert. No data loss, no silent failures.

---

## Claude's Discretion

- Redis health key design (key names, TTLs, update frequency)
- DB migration 010 specifics
- Consumer logging verbosity beyond explicit decisions
- opticodds_status model column mapping details

## Deferred Ideas

- REST API queue endpoints (/api/v1/opticodds/queue/start|stop|status) — self-managing consumer sufficient for now
- Health badge UI — ships in Phase 14 per ROADMAP; Phase 12 only sets up Redis health keys
