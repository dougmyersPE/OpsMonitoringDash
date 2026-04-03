# Phase 14: Dashboard and Health - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-03
**Phase:** 14-dashboard-and-health
**Areas discussed:** Health Badge Presentation, OpticOdds Column Display, Schema & API Plumbing, Column Positioning
**Mode:** auto (all decisions auto-selected)

---

## Health Badge Presentation

| Option | Description | Selected |
|--------|-------------|----------|
| Mirror WS badge pattern | Dedicated inline block after WS badge, with `opticOddsTitle()` helper | ✓ |
| Add to WORKERS array | Would require changing array to support object-type health | |

**User's choice:** [auto] Mirror WS badge pattern (recommended default)
**Notes:** Backend already returns `opticodds_consumer` in same `{connected, state, since}` shape as `ws_prophetx`

| Option | Description | Selected |
|--------|-------------|----------|
| "OpticOdds" | Full source name, clear to operators | ✓ |
| "OO" | Short abbreviation | |
| "RMQ" | Technical abbreviation | |

**User's choice:** [auto] "OpticOdds" (recommended default)

---

## OpticOdds Column Display

| Option | Description | Selected |
|--------|-------------|----------|
| Reuse SourceStatus component | Consistent with other source columns; special statuses show in amber | ✓ |
| Custom component | Could highlight walkover/retired/suspended differently | |

**User's choice:** [auto] Reuse SourceStatus component (recommended default)
**Notes:** SourceStatus already handles null (shows "Not Listed"), Live, Ended, Not Started, and flag-worthy statuses in amber

---

## Schema & API Plumbing

| Option | Description | Selected |
|--------|-------------|----------|
| Single-pass addition | Add opticodds_status to EventResponse + EventRow + SortCol + STATUS_COLS together | ✓ |

**User's choice:** [auto] Single-pass addition (recommended default)
**Notes:** compute_is_critical already accepts 6 params (Phase 13). Event model already has column (Phase 12).

---

## Column Positioning

| Option | Description | Selected |
|--------|-------------|----------|
| After OddsBlaze, before Flag | Last source column, natural extension of source sequence | ✓ |
| After ESPN, before OddsBlaze | Alphabetical ordering | |
| First source column | Emphasize new data source | |

**User's choice:** [auto] After OddsBlaze, before Flag (recommended default)

---

## Claude's Discretion

- Whether to rename `WsProphetXHealth` interface to generic `ConsumerHealth`
- colSpan update on empty-state row (11 → 12)
- Minor TypeScript type refinements

## Deferred Ideas

None — discussion stayed within phase scope
