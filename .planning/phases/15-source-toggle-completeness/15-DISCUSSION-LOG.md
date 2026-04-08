# Phase 15: Source Toggle Completeness - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-07
**Phase:** 15-source-toggle-completeness
**Areas discussed:** ProphetX WS toggle behavior, Seed data & migration

---

## ProphetX WS Toggle Behavior

### Toggle check location

| Option | Description | Selected |
|--------|-------------|----------|
| Per-message check | Call is_source_enabled('prophetx_ws') at top of _upsert_event(). Immediate response, 1 DB read per message. | ✓ |
| Cached periodic check | Cache toggle state in module-level var, refresh via timer thread. Less responsive but zero DB reads per message. | |
| You decide | Claude picks based on codebase patterns. | |

**User's choice:** Per-message check (Recommended)
**Notes:** Consistent with how all other workers check the toggle.

### Clear existing data when disabled

| Option | Description | Selected |
|--------|-------------|----------|
| No — skip writes only | ProphetX is primary source of truth. Clearing would leave events with no status. Just stop new writes. | ✓ |
| Yes — clear like other sources | Consistent with OddsBlaze/OpticOdds. NULL out prophetx_status and recompute. poll_prophetx still writes. | |
| You decide | Claude picks based on source's role. | |

**User's choice:** No — skip writes only (Recommended)
**Notes:** ProphetX status is authoritative; clearing would be destructive.

### Poll fallback when WS disabled

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — poll takes over | poll_prophetx ignores WS authority window and writes freely when WS toggle is off. | ✓ |
| No — independent toggles | WS toggle only affects WS writes. poll_prophetx keeps authority-window logic unchanged. | |
| You decide | Claude picks based on authority model. | |

**User's choice:** Yes — poll takes over (Recommended)
**Notes:** Ensures events still get status updates from REST API when WS writes are disabled.

---

## Seed Data & Migration

### Seed method

| Option | Description | Selected |
|--------|-------------|----------|
| Seed script only | Add to SOURCE_ENABLED_DEFAULTS in seed.py. Existing idempotent pattern. No migration needed. | ✓ |
| Alembic migration | INSERT rows via data migration. More explicit but heavier for config rows. | |
| Both seed + migration | Migration for production, seed for fresh deploys. | |

**User's choice:** Seed script only (Recommended)
**Notes:** system_config is a key-value table; seed script handles this cleanly.

### Default state for new toggles

| Option | Description | Selected |
|--------|-------------|----------|
| All enabled | source_enabled_opticodds=true, source_enabled_prophetx_ws=true. Matches existing sources. | ✓ |
| WS disabled, OpticOdds enabled | Start with WS disabled since it's new toggle behavior. | |
| You decide | Claude picks based on deployment safety. | |

**User's choice:** All enabled (Recommended)
**Notes:** No behavioral change on deploy.

---

## Claude's Discretion

- UI ordering of 6 sources in the toggle table
- Whether to add source type labels (poll/stream)
- Log message format when WS writes skipped

## Deferred Ideas

None — discussion stayed within phase scope
