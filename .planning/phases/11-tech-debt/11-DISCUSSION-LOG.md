# Phase 11: Tech Debt - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-01
**Phase:** 11-tech-debt
**Areas discussed:** Removal strategy, Source coverage, Roadmap updates, Match logic

---

## Initial Gray Areas Presented

| Option | Description | Selected |
|--------|-------------|----------|
| Multi-URL strategy | How to handle SportsApiClient needing 5 base URLs vs BaseAPIClient's single URL | |
| Error handling | SportsApiClient catches all → returns []; BaseAPIClient retries then propagates | |
| Quota capture | Inline Redis writes vs _capture_quota_headers hook | |
| DEBT-02 bundling | Bundle Redis MGET batching into this phase | |

**User's choice:** None of the above — user proposed removing Sports API entirely instead of refactoring it.
**Notes:** "Can we just remove the Sports API actually. I think it's a better use of resources."

---

## Removal Motivation

| Option | Description | Selected |
|--------|-------------|----------|
| Redundant data | SportsDataIO, ESPN, OddsBlaze cover same sports | |
| API cost / quota | Not worth the coverage it provides | |
| Both | Redundant AND not worth the cost | ✓ |

**User's choice:** Both
**Notes:** None

---

## Removal Depth

| Option | Description | Selected |
|--------|-------------|----------|
| Full removal (Recommended) | Drop DB column, remove worker, usage page, health checks, mismatch detector | ✓ |
| Stop polling only | Remove worker + client but leave DB column and usage history | |

**User's choice:** Full removal
**Notes:** None

---

## Source Coverage After Removal

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, sufficient | 3 sources enough — Sports API was least reliable | ✓ |
| Let me think | Review each source's coverage first | |

**User's choice:** Yes, sufficient
**Notes:** None

---

## Roadmap Update

| Option | Description | Selected |
|--------|-------------|----------|
| Update roadmap (Recommended) | Rewrite Phase 11 goal and DEBT-01 to reflect removal | ✓ |
| Note in context only | Keep DEBT-01 as-is, explain pivot in CONTEXT.md | |

**User's choice:** Update roadmap
**Notes:** None

---

## Match Logic Cleanup

| Option | Description | Selected |
|--------|-------------|----------|
| You decide | Claude has discretion — cleanest logic after removal | ✓ |
| Tighten logic | Recalibrate match thresholds/weights | |

**User's choice:** You decide (Claude's discretion)
**Notes:** None

---

## Claude's Discretion

- Match logic cleanup after sports_api_status column removal (compute_status_match, compute_is_critical)

## Deferred Ideas

- DEBT-02 (Redis MGET batching) — remains future requirement, not bundled
