---
phase: 03-dashboard-and-alerts
plan: "03"
subsystem: notifications
tags: [fastapi, sqlalchemy, react, tanstack-query, shadcn, typescript, notifications]

# Dependency graph
requires:
  - phase: 02-monitoring-engine
    provides: Notification SQLAlchemy model (notification.py) + SyncSessionLocal for DB writes
  - phase: 03-dashboard-and-alerts
    plan: "01"
    provides: React SPA scaffold, shadcn/ui components, TanStack Query setup, queryKey ['notifications'] convention
  - phase: 03-dashboard-and-alerts
    plan: "02"
    provides: send_alerts.py Celery task with Redis SETNX dedup that fires on alerts
provides:
  - GET /api/v1/notifications — list all notifications newest-first (limit 100) with unread_count
  - PATCH /api/v1/notifications/{id}/read — mark single notification as read
  - PATCH /api/v1/notifications/mark-all-read — mark all unread as read
  - NotificationCenter React component with Bell icon, unread badge, Sheet sliding panel, mark-read actions
  - send_alerts.py now writes Notification DB row after dedup check (before Slack delivery)
affects:
  - 03-04-PLAN.md (final polish plan — notification center is now complete)

# Tech tracking
tech-stack:
  added:
    - shadcn/ui Sheet component (frontend/src/components/ui/sheet.tsx, via `npx shadcn@latest add sheet`)
  patterns:
    - FastAPI route ordering: PATCH /mark-all-read defined before PATCH /{notification_id}/read — prevents path conflict where "mark-all-read" would be interpreted as a UUID
    - Notification DB write in Celery sync task uses SyncSessionLocal context manager with explicit commit
    - TanStack Query invalidation after mutations: onSuccess calls queryClient.invalidateQueries({ queryKey: ['notifications'] })

key-files:
  created:
    - backend/app/schemas/notification.py
    - backend/app/api/v1/notifications.py
    - frontend/src/api/notifications.ts
    - frontend/src/components/NotificationCenter.tsx
    - frontend/src/components/ui/sheet.tsx
  modified:
    - backend/app/main.py (added notifications router import + include_router)
    - backend/app/workers/send_alerts.py (added Notification DB write + imports)
    - frontend/src/pages/DashboardPage.tsx (added NotificationCenter to header)

key-decisions:
  - "PATCH /mark-all-read route defined before PATCH /{notification_id}/read in FastAPI router — FastAPI matches routes in order; if id route comes first, string 'mark-all-read' would be interpreted as a UUID causing 422"
  - "Notification DB write placed before Slack guard in send_alerts.py — ensures in-app notifications appear even when SLACK_WEBHOOK_URL is not configured"
  - "Sheet component installed via `npx shadcn@latest add sheet` (Rule 3 auto-fix) — was not installed in Plan 03-01 but required for NotificationCenter sliding panel"

patterns-established:
  - "Route ordering safety: collection-action routes (mark-all-read) must precede parameterized routes (/{id}/read) in FastAPI"
  - "Celery task DB writes: use SyncSessionLocal context manager, add model instance, explicit commit before returning"

requirements-completed: [NOTIF-01]

# Metrics
duration: 3min
completed: 2026-02-26
---

# Phase 3 Plan 03: In-App Notification Center Summary

**FastAPI notification CRUD endpoints (list + mark-read) wired to Celery send_alerts task, plus React NotificationCenter with Bell icon, unread badge, and shadcn Sheet sliding panel**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-26T15:21:34Z
- **Completed:** 2026-02-26T15:24:11Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments
- Backend: GET /api/v1/notifications returns all notifications newest-first with unread_count; PATCH endpoints mark single and all-read
- Celery: send_alerts.py now writes a Notification DB row for every deduplicated alert, before the Slack guard, so in-app center works even without Slack
- Frontend: NotificationCenter component renders Bell icon with red badge in dashboard header; Sheet slides from right showing all notifications with blue-50 unread highlight and mark-read buttons

## Task Commits

Each task was committed atomically:

1. **Task 1: Notifications Backend API and send_alerts DB Write** - `5856982` (feat)
2. **Task 2: NotificationCenter React Component** - `f63db9d` (feat)

## Files Created/Modified
- `backend/app/schemas/notification.py` - NotificationResponse and NotificationListResponse Pydantic schemas
- `backend/app/api/v1/notifications.py` - GET /notifications, PATCH /{id}/read, PATCH /mark-all-read routes
- `backend/app/main.py` - Added notifications router import + include_router call
- `backend/app/workers/send_alerts.py` - Added Notification DB write (uuid, SyncSessionLocal imports + write block)
- `frontend/src/api/notifications.ts` - fetchNotifications(), markRead(), markAllRead() with typed interfaces
- `frontend/src/components/NotificationCenter.tsx` - Bell icon + unread Badge + Sheet panel + mark-read mutations
- `frontend/src/components/ui/sheet.tsx` - shadcn/ui Sheet component (Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger)
- `frontend/src/pages/DashboardPage.tsx` - Added NotificationCenter import + placement in header flex container

## Decisions Made
- PATCH /mark-all-read route declared before PATCH /{notification_id}/read in the FastAPI router. FastAPI evaluates routes in declaration order; placing the parameterized route first would cause FastAPI to interpret the literal string "mark-all-read" as a UUID, returning a 422 validation error.
- Notification DB write placed before the `if not settings.SLACK_WEBHOOK_URL:` guard. This ensures notifications appear in the in-app center even when Slack is not configured, which is the common development environment case.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Installed missing shadcn/ui Sheet component**
- **Found during:** Task 2 (NotificationCenter component creation)
- **Issue:** `sheet.tsx` not present in `frontend/src/components/ui/` — it was not installed during Plan 03-01. NotificationCenter imports `Sheet`, `SheetContent`, `SheetHeader`, `SheetTitle`, `SheetTrigger` from `@/components/ui/sheet`, which would cause TypeScript build failure.
- **Fix:** Ran `npx shadcn@latest add sheet --yes` in frontend directory
- **Files modified:** `frontend/src/components/ui/sheet.tsx` (created)
- **Verification:** `npm run build` exits 0 with 2281 modules transformed
- **Committed in:** `f63db9d` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 3 - Blocking)
**Impact on plan:** Required for build to pass. No scope creep.

## Issues Encountered
- Docker backend container does not volume-mount source code — new Python modules are not importable in the running container without a rebuild. Import verification was done via AST syntax check using the local `.venv` Python interpreter instead of the full runtime import chain.

## User Setup Required
None - no external service configuration required. The notifications feature works without Slack configuration (DB writes happen regardless).

## Next Phase Readiness
- Notification center is fully wired: backend routes, Celery DB write, frontend component all complete
- SSE hook in useSse already calls `queryClient.invalidateQueries(['notifications'])` on update events — notification list auto-refreshes when alerts fire
- Plan 03-04 (final polish) can proceed — all three core features (dashboard, SSE/alerting, notification center) are complete

---
*Phase: 03-dashboard-and-alerts*
*Completed: 2026-02-26*

## Self-Check: PASSED

- `backend/app/api/v1/notifications.py` — EXISTS
- `backend/app/schemas/notification.py` — EXISTS
- `frontend/src/api/notifications.ts` — EXISTS
- `frontend/src/components/NotificationCenter.tsx` — EXISTS
- `frontend/src/components/ui/sheet.tsx` — EXISTS
- Task 1 commit `5856982` — verified in git log
- Task 2 commit `f63db9d` — verified in git log
- `npm run build` exits 0 with 2281 modules transformed, zero TypeScript errors
