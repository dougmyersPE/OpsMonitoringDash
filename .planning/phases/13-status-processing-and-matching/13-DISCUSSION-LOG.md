# Phase 13: Status Processing and Matching - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-03
**Phase:** 13-status-processing-and-matching
**Areas discussed:** Fuzzy matching strategy, Special status alerting, Redis key alignment, Mismatch detection integration
**Mode:** Auto (all decisions auto-selected from recommended defaults)

---

## Fuzzy Matching Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Mirror poll_oddsblaze.py | Name token overlap + 24h date window (proven pattern) | ✓ |
| Mirror poll_espn.py | Substring match + fuzzy fallback (more complex) | |
| New approach | Custom matching logic for tennis specifics | |

**User's choice:** [auto] Mirror poll_oddsblaze.py pattern (recommended default)
**Notes:** Proven pattern used by OddsBlaze and ESPN workers. Tennis matches have clear competitor names which work well with token overlap scoring.

---

## Special Status Alerting

| Option | Description | Selected |
|--------|-------------|----------|
| Dedicated alert for walkover/retired/suspended | Separate Slack alert with event context (reuse dedup pattern) | ✓ |
| Combine with unknown status alerts | Single alert path for all unusual statuses | |
| Log-only | No Slack alert, just WARNING logs | |

**User's choice:** [auto] Dedicated alert (recommended default)
**Notes:** TNNS-03 explicitly requires Slack alerts for these statuses. They are known but operationally significant — operators need to see them immediately, separate from the unknown-status noise.

---

## Redis Key Alignment

| Option | Description | Selected |
|--------|-------------|----------|
| Keep opticodds: prefix | Already deployed in Phase 12, wired to health endpoint | ✓ |
| Rename to rmq: prefix | Matches ROADMAP description but requires migration | |

**User's choice:** [auto] Keep opticodds: prefix (recommended default)
**Notes:** Phase 12 implemented with opticodds: prefix consistently. Health endpoint already reads these keys. Changing to rmq: would break deployed infrastructure for no functional gain. AMQP-03 requirement is satisfied.

---

## Mismatch Detection Integration

| Option | Description | Selected |
|--------|-------------|----------|
| Add 6th param to compute_status_match | opticodds_status param, NULL-safe, + _OPTICODDS_CANONICAL dict | ✓ |
| Separate tennis-only mismatch function | New function for tennis events only | |

**User's choice:** [auto] Add 6th parameter (recommended default)
**Notes:** Follows the exact pattern used when oddsblaze was added (5th param). Consistent API, NULL-safe for non-tennis events.

---

## Claude's Discretion

- Exact fuzzy match threshold
- DB session lifecycle (per-message vs batched)
- Logging verbosity for match hits/misses
- Test structure

## Deferred Ideas

- Dashboard OpticOdds column (Phase 14 — DASH-02)
- OpticOdds health badge (Phase 14 — DASH-01)
