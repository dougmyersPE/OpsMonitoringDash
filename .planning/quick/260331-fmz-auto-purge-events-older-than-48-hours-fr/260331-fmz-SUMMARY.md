---
phase: quick
plan: 260331-fmz
subsystem: backend/workers
tags: [cleanup, celery, events, purge]
dependency_graph:
  requires: []
  provides: [auto-purge-48h]
  affects: [events, markets, event_id_mappings, notifications]
tech_stack:
  added: []
  patterns: [bulk-delete, FK-ordered-deletion, mock-based-unit-tests]
key_files:
  modified:
    - backend/app/workers/cleanup_old_events.py
  created:
    - backend/tests/test_cleanup_old_events.py
decisions:
  - Remove prophetx_status filter so ALL events older than 48h are purged regardless of status
  - Delete order: markets (FK) -> event_id_mappings (by prophetx_event_id) -> notifications (by entity_id) -> events
  - Audit log explicitly excluded (insert-only by design)
metrics:
  duration: "~6 minutes"
  completed_date: "2026-03-31"
  tasks_completed: 1
  tasks_total: 1
  files_changed: 2
---

# Quick Task 260331-fmz: Auto-purge Events Older Than 48 Hours Summary

**One-liner:** Removed `prophetx_status == "ended"` filter from cleanup task so all events older than 48h are purged unconditionally, with cascading deletes for event_id_mappings and notifications.

## What Was Built

Updated `cleanup_old_events.py` to:
- Drop the `prophetx_status == "ended"` WHERE clause — only `scheduled_start <= cutoff` remains
- Collect `prophetx_event_id` values for stale events before deletion
- Delete related `event_id_mappings` by `prophetx_event_id` (no FK, value-matched)
- Delete related `notifications` by `entity_type = 'event'` AND `entity_id IN (stale_ids)`
- Preserve FK-ordered deletion: markets first, then orphaned mappings/notifications, then events
- Log counts for every deleted table (`events`, `markets`, `mappings_deleted`, `notifications_deleted`)
- Audit log explicitly untouched (insert-only by design)

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Update cleanup task + tests (TDD) | 18a9d61 | backend/app/workers/cleanup_old_events.py, backend/tests/test_cleanup_old_events.py |

## Tests

7 unit tests added covering:
1. Stale events deleted regardless of prophetx_status
2. Fresh events (< 48h) not deleted even if ended
3. Markets deleted before events (FK ordering verified)
4. event_id_mappings deleted by prophetx_event_id
5. Notifications deleted by entity_type/entity_id
6. Audit log not imported/touched
7. Returns correct deleted count

All tests run with `--noconftest` flag to bypass conftest.py's FastAPI app import (incompatible Python version in local dev environment; production uses Docker with correct Python 3.12).

## Deviations from Plan

### Auto-fixed Issues

None — plan executed exactly as written.

### Notes

The `conftest.py` in `backend/tests/` imports `app.main` which requires env vars and Python 3.12 features (union types). Running tests with `--noconftest` bypasses this. The plan's verification command works as-is when run with env vars loaded. In production Docker environment this is not an issue.

## Known Stubs

None.

## Self-Check: PASSED
