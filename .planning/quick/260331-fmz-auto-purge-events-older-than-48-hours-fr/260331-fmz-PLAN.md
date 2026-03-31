---
phase: quick
plan: 260331-fmz
type: execute
wave: 1
depends_on: []
files_modified:
  - backend/app/workers/cleanup_old_events.py
  - backend/tests/test_cleanup_old_events.py
autonomous: true
requirements: [auto-purge-48h]
must_haves:
  truths:
    - "Events older than 48 hours are deleted regardless of prophetx_status"
    - "Related markets, event_id_mappings, and notifications are cleaned up"
    - "Cleanup runs automatically every 6 hours via existing Celery Beat schedule"
  artifacts:
    - path: "backend/app/workers/cleanup_old_events.py"
      provides: "Purge task that deletes all events older than 48h"
    - path: "backend/tests/test_cleanup_old_events.py"
      provides: "Unit tests for cleanup logic"
  key_links:
    - from: "backend/app/workers/cleanup_old_events.py"
      to: "celery_app beat_schedule"
      via: "existing 'cleanup-old-events' schedule entry (every 6h at :15)"
---

<objective>
Update the existing cleanup_old_events Celery task to purge ALL events older than 48 hours,
not just those with prophetx_status == "ended". Also clean up orphaned related records
(event_id_mappings, notifications) that reference deleted events.

Purpose: Dashboard accumulates stale events that clutter the UI and waste DB space. Events
older than 48 hours are no longer operationally relevant regardless of their status.

Output: Updated cleanup task + tests confirming the behavior.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@backend/app/workers/cleanup_old_events.py
@backend/app/workers/celery_app.py
@backend/app/models/event.py
@backend/app/models/market.py
@backend/app/models/event_id_mapping.py
@backend/app/models/notification.py
@backend/app/models/audit_log.py

<interfaces>
From backend/app/models/event.py:
- Event.id (UUID PK), Event.scheduled_start (DateTime), Event.prophetx_status (String)
- Event.prophetx_event_id (String, unique)

From backend/app/models/market.py:
- Market.event_id (FK -> events.id)

From backend/app/models/event_id_mapping.py:
- EventIDMapping.prophetx_event_id (String, no FK — matched by value)

From backend/app/models/notification.py:
- Notification.entity_id (UUID, no FK — matched by value to Event.id)
- Notification.entity_type (String — filter on "event")

From backend/app/models/audit_log.py:
- AuditLog — INSERT-only, NEVER delete. Do not touch audit_log rows.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Update cleanup task to purge all events older than 48h</name>
  <files>backend/app/workers/cleanup_old_events.py, backend/tests/test_cleanup_old_events.py</files>
  <behavior>
    - Test 1: Events with scheduled_start > 48h ago are deleted regardless of prophetx_status (ended, live, not_started, None)
    - Test 2: Events with scheduled_start < 48h ago are NOT deleted even if ended
    - Test 3: Related markets (FK) are deleted before events
    - Test 4: Related event_id_mappings (matched by prophetx_event_id) are deleted
    - Test 5: Related notifications (entity_type="event", entity_id=event.id) are deleted
    - Test 6: Audit log rows are NOT deleted (insert-only table)
    - Test 7: Returns count of deleted events
  </behavior>
  <action>
    1. Update cleanup_old_events.py:
       - Remove the `Event.prophetx_status == "ended"` filter from the WHERE clause.
         Keep only `Event.scheduled_start <= cutoff` (48h ago).
       - After finding stale event IDs, also collect their prophetx_event_ids.
       - Delete related event_id_mappings WHERE prophetx_event_id IN (stale prophetx_event_ids).
       - Delete related notifications WHERE entity_type = 'event' AND entity_id IN (stale_ids).
       - Keep existing Market deletion (FK constraint requires it before Event deletion).
       - Do NOT touch audit_log (insert-only by design).
       - Log counts for each table cleaned up (events, markets, mappings, notifications).

    2. Create test file backend/tests/test_cleanup_old_events.py:
       - Use pytest with SQLAlchemy in-memory or test DB fixtures matching project patterns.
       - Check existing test files for DB session fixture patterns (e.g., test_update_event_status.py).
       - Write tests for all behaviors listed above.
  </action>
  <verify>
    <automated>cd /Users/doug/OpsMonitoringDash/backend && python -m pytest tests/test_cleanup_old_events.py -x -v 2>&1 | tail -30</automated>
  </verify>
  <done>
    - cleanup_old_events.run() deletes ALL events older than 48h (no status filter)
    - Related markets, event_id_mappings, and notifications are cleaned up
    - Audit log is untouched
    - All tests pass
  </done>
</task>

</tasks>

<verification>
- Run cleanup task test suite: `cd backend && python -m pytest tests/test_cleanup_old_events.py -x -v`
- Verify no import errors: `cd backend && python -c "from app.workers.cleanup_old_events import run; print('OK')"`
- Confirm celery_app.py still includes the task and schedule is unchanged (no edits needed there)
</verification>

<success_criteria>
- Events older than 48 hours are purged regardless of status
- Related records (markets, mappings, notifications) cleaned up; audit_log untouched
- Existing Celery Beat schedule (every 6h) drives the task — no schedule changes needed
- Tests confirm all behaviors
</success_criteria>

<output>
After completion, create `.planning/quick/260331-fmz-auto-purge-events-older-than-48-hours-fr/260331-fmz-SUMMARY.md`
</output>
