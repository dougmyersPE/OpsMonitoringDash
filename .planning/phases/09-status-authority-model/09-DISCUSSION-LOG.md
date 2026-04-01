# Phase 9: Status Authority Model - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-31
**Phase:** 09-status-authority-model
**Areas discussed:** Authority window, status_source storage, Stale event handling, Reconciliation behavior
**Mode:** auto (all decisions auto-selected from recommended defaults)

---

## Authority Window (AUTH-02)

| Option | Description | Selected |
|--------|-------------|----------|
| 5 minutes | Shorter window, poll takes over sooner | |
| 10 minutes (configurable) | Matches ROADMAP success criteria; configurable for tuning | ✓ |
| 30 minutes | Longer protection, but risks stale WS data persisting | |

**User's choice:** 10 minutes (configurable) [auto-selected]
**Notes:** ROADMAP success criteria explicitly states "within 10 minutes" as the validation threshold.

---

## status_source Storage (AUTH-01)

| Option | Description | Selected |
|--------|-------------|----------|
| Column on events table | Simple, directly queryable, no joins | ✓ |
| Separate audit/history table | Full history of all source changes | |

**User's choice:** Column on events table [auto-selected]
**Notes:** AUTH-01 requires the column "visible in DB" — a single column satisfies this. Audit history is a future requirement (WSOPS-02) if needed.

---

## Stale Event Handling

| Option | Description | Selected |
|--------|-------------|----------|
| Authority protects all statuses | Poll cannot overwrite anything during window | |
| No protection for "ended" | Terminal status always applies regardless of authority | ✓ |

**User's choice:** No protection for "ended" [auto-selected]
**Notes:** "ended" is terminal in the event lifecycle. Blocking poll from marking ended would leave ghost events.

---

## Reconciliation Behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Log and skip overwrite | Audit trail, WS wins during window | ✓ |
| Silently skip | No log, just don't overwrite | |
| Queue for manual review | Flag discrepancies for operator attention | |

**User's choice:** Log and skip overwrite [auto-selected]
**Notes:** Structured logging gives operators visibility without requiring action. Discrepancies are expected during normal operation.

---

## Claude's Discretion

- Migration design and numbering
- Structured log format for authority skips
- Test file organization
- Index decisions on new columns

## Deferred Ideas

None
