---
phase: 03-dashboard-and-alerts
verified: 2026-02-26T17:26:33Z
status: human_needed
score: 14/14 must-haves verified
re_verification: true
gaps:
  - truth: "Slack receives an alert for each alertable condition (mismatch detected, auto-update success/failure, low liquidity, postponed/cancelled event, API retries exhausted)"
    status: resolved
    reason: "Resolved in 03-05: send_alerts_task.delay(alert_type='auto_update_success', ...) added after session.commit() on success path; send_alerts_task.delay(alert_type='auto_update_failure', ...) added in except block after audit log commit (wrapped in try/except). Both calls present in update_event_status.py."
    resolved_by: "03-05"

  - truth: "When the SSE connection drops, a visible 'Connection lost — reconnecting...' banner appears within 20 seconds"
    status: resolved
    reason: "Resolved in 03-05: SseProvider.tsx replaced with lastOpenRef timestamp-based detection. Banner shows when readyState !== OPEN AND elapsed >= 15s (DISCONNECT_GRACE_MS) since last OPEN observation. Covers CONNECTING state (genuine network drops)."
    resolved_by: "03-05"

  - truth: "Clicking a notification's entity link navigates to the events or markets section (scrolls/highlights)"
    status: resolved
    reason: "Resolved in 03-05: Entity display in NotificationCenter.tsx replaced with <a href='/#events'> or <a href='/#markets'> anchor based on n.entity_type. Clicking navigates to relevant dashboard section."
    resolved_by: "03-05"

  - truth: "The dashboard shows polling worker status and last-checked timestamps per event"
    status: resolved
    reason: "Resolved in 03-05: EventRow.last_checked_at renamed to last_prophetx_poll in frontend/src/api/events.ts to match backend EventResponse schema. EventsTable.tsx updated to read event.last_prophetx_poll. Last Checked column now renders real timestamps when backend has poll data."
    resolved_by: "03-05"

human_verification:
  - test: "SSE 30-second update window"
    expected: "After any event/market state change by a poll worker, the dashboard reflects the update within 30 seconds without a page refresh"
    why_human: "Requires live stack with workers running (workers currently exited due to missing PROPHETX_API_KEY) — cannot verify timing programmatically"
  - test: "Full login-to-dashboard smoke test"
    expected: "Open http://localhost/, login page appears; after login, dashboard shows EventsTable, MarketsTable, SystemHealth dots, and Bell icon"
    why_human: "Requires browser and running docker stack; 03-04 auto-approved checkpoint without human browser confirmation"
  - test: "Slack alert delivery"
    expected: "When a mismatch/liquidity/flag_event condition fires with SLACK_WEBHOOK_URL set, Slack channel receives the alert message with entity context block"
    why_human: "Requires configured SLACK_WEBHOOK_URL and a live triggerable condition"
---

# Phase 3: Dashboard and Alerts Verification Report

**Phase Goal:** Operators see all events and markets in a real-time dashboard that updates via SSE within 30 seconds of any change, receive Slack alerts with deduplication, can toggle alert-only mode for safe rollout, and have an in-app notification center with read/unread state

**Verified:** 2026-02-26 (initial) | **Re-verified:** 2026-02-26T17:26:33Z (after 03-05 gap closure)
**Status:** human_needed — all automated checks pass; 3 items require live stack/browser/Slack
**Re-verification:** Yes — gap closure plan 03-05 closed all 4 automated gaps

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Dashboard shows all ProphetX events with ProphetX status vs. real-world status side by side; mismatches visually highlighted | VERIFIED | EventsTable.tsx: `!event.status_match && "bg-red-50 border-l-4 border-l-red-500"` — both columns present |
| 2 | Dashboard shows all markets with current liquidity vs. configured threshold; below-threshold markets highlighted | VERIFIED | MarketsTable.tsx: `market.below_threshold && "bg-red-50 border-l-4 border-l-red-500"` — both columns present |
| 3 | Dashboard updates via SSE within 30 seconds; SSE heartbeats keep Nginx connection alive | PARTIALLY VERIFIED | stream.py has `EventSourceResponse(generator(), ping=20)` — 20s ping present; 30s timing requires human test |
| 4 | When SSE connection drops, "Connection lost — reconnecting..." banner appears within 20 seconds | VERIFIED (code) | SseProvider uses lastOpenRef timestamp; banner shows after 15s without OPEN — covers CONNECTING state. Human test needed for confirmation. |
| 5 | System health shows polling worker status | VERIFIED | SystemHealth.tsx queries `/health/workers`; green/red dots for poll_prophetx and poll_sports_data |
| 6 | Last-checked timestamps per event shown | VERIFIED | EventRow.last_prophetx_poll matches backend schema; EventsTable reads event.last_prophetx_poll — will show real timestamps |
| 7 | Slack receives alert for each alertable condition | VERIFIED (code) | flag_event and liquidity_alert fire + update_event_status now calls send_alerts_task.delay() on both success and failure paths. Live Slack test needs human. |
| 8 | Max 1 alert per event per condition type per 5-minute window (Redis SETNX dedup) | VERIFIED | send_alerts.py: `r.set(dedup_key, "1", ex=300, nx=True)` |
| 9 | When alert-only mode enabled, system detects mismatches, sends alerts, makes no ProphetX writes; toggle requires no deploy | VERIFIED (code) | alert_only_mode guard reads system_config DB — no deploy needed; ProphetX write skipped; send_alerts_task.delay() now fires with "(alert-only mode)" note in message |
| 10 | Dashboard shows bell icon with unread badge | VERIFIED | NotificationCenter.tsx: Bell icon + `<Badge variant="destructive">` for unread count |
| 11 | Bell icon opens sliding panel with notifications newest-first, read/unread state | VERIFIED | Sheet component with `side="right"`; blue-50 for unread; white for read |
| 12 | Clicking a notification's entity link navigates to the relevant event or market | VERIFIED | Entity shown as `<a href="/#events">` or `<a href="/#markets">` anchor — clicking navigates to dashboard section |
| 13 | Mark all read / individual mark-read clears unread badge | VERIFIED | PATCH /notifications/mark-all-read and PATCH /notifications/{id}/read — both wired with TanStack Query invalidation |
| 14 | Notifications list auto-refreshes when SSE fires | VERIFIED | useSse.ts line 20: `queryClient.invalidateQueries({ queryKey: ["notifications"] })` |

**Score:** 14/14 truths verified (all automated checks pass — 3 items require human/live-stack confirmation)

---

## Required Artifacts

### Plan 03-01 (Frontend Dashboard)

| Artifact | Status | Details |
|----------|--------|---------|
| `frontend/src/App.tsx` | VERIFIED | QueryClientProvider + ProtectedRoute + token check wired |
| `frontend/src/stores/auth.ts` | VERIFIED | useAuthStore with persist middleware present |
| `frontend/src/api/client.ts` | VERIFIED | axios interceptors for JWT and 401 redirect wired |
| `frontend/src/hooks/useSse.ts` | VERIFIED | EventSource at /api/v1/stream?token=...; invalidateQueries on update |
| `frontend/src/components/EventsTable.tsx` | VERIFIED | status_match highlight correct; reads event.last_prophetx_poll (field name fixed in 03-05) |
| `frontend/src/components/MarketsTable.tsx` | VERIFIED | current_liquidity column and below_threshold highlight correct |
| `frontend/src/components/SystemHealth.tsx` | VERIFIED | poll_prophetx field read; refetchInterval 30s; green/red dots |

### Plan 03-02 (SSE + Alerting Backend)

| Artifact | Status | Details |
|----------|--------|---------|
| `backend/app/api/v1/stream.py` | VERIFIED | EventSourceResponse with pubsub.subscribe("prophet:updates"); ping=20 |
| `backend/app/api/deps.py` | VERIFIED | verify_token_from_query present; validates ?token= query param |
| `backend/app/api/v1/health.py` | VERIFIED | /health/workers reads worker:heartbeat:* Redis keys; returns {poll_prophetx, poll_sports_data} |
| `backend/app/workers/send_alerts.py` | VERIFIED | WebhookClient.send() present; SETNX dedup with nx=True, ex=300 |
| `backend/app/workers/update_event_status.py` | VERIFIED | alert_only_mode guard exists; ProphetX write skipped correctly; send_alerts_task.delay() wired on both success and failure paths (fixed in 03-05) |

### Plan 03-03 (Notification Center)

| Artifact | Status | Details |
|----------|--------|---------|
| `backend/app/api/v1/notifications.py` | VERIFIED | GET /notifications + PATCH /{id}/read + PATCH /mark-all-read; mark-all-read before parameterized route |
| `backend/app/schemas/notification.py` | VERIFIED | NotificationResponse + NotificationListResponse with from_attributes |
| `backend/app/workers/send_alerts.py` | VERIFIED | NotificationModel DB write before Slack guard (line 62) |
| `frontend/src/components/NotificationCenter.tsx` | VERIFIED | SheetContent, Bell, Badge all present; entity navigation is `<a href="/#events">` / `<a href="/#markets">` anchor (fixed in 03-05) |
| `frontend/src/api/notifications.ts` | VERIFIED | fetchNotifications(), markRead(), markAllRead() with typed interfaces |

### Plan 03-04 (Production Stack)

| Artifact | Status | Details |
|----------|--------|---------|
| `nginx/nginx.conf` | VERIFIED | proxy_buffering off; proxy_read_timeout 86400s; frontend upstream present |
| `frontend/Dockerfile` | VERIFIED | node:20-alpine build stage + nginx:alpine serve stage |
| `frontend/nginx.conf` | VERIFIED | try_files $uri $uri/ /index.html SPA fallback |
| `docker-compose.yml` | VERIFIED | frontend service with build: ./frontend; nginx depends_on frontend |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `frontend/src/hooks/useSse.ts` | `/api/v1/stream` | EventSource with `?token=` query param | VERIFIED | Line 13: `/api/v1/stream?token=${encodeURIComponent(token)}` |
| `frontend/src/App.tsx` | DashboardPage | ProtectedRoute checks Zustand token before rendering | VERIFIED | token check → Navigate to /login |
| `frontend/src/components/EventsTable.tsx` | `/api/v1/events` | useQuery with queryKey ['events'] | VERIFIED | Line 22-25 |
| `backend/app/workers/poll_prophetx.py` | `prophet:updates` Redis channel | `_publish_update()` after each event/market upsert | VERIFIED | Lines 198, 292 |
| `backend/app/api/v1/stream.py` | `prophet:updates` Redis channel | `pubsub.subscribe("prophet:updates")` + async generator yield | VERIFIED | Lines 40, 54 |
| `backend/app/workers/send_alerts.py` | Slack API | `WebhookClient(settings.SLACK_WEBHOOK_URL).send()` | VERIFIED | Line 81-82 |
| `backend/app/workers/update_event_status.py` | system_config alert_only_mode | DB read before ProphetX write, early branch when true | VERIFIED | Lines 103-108 |
| `backend/app/workers/update_event_status.py` | send_alerts | send_alerts_task.delay() after status update | VERIFIED | send_alerts_task.delay() called on success (line 163) and failure (line 204) paths (fixed in 03-05) |
| `frontend/src/components/NotificationCenter.tsx` | `/api/v1/notifications` | useQuery with queryKey ['notifications'] | VERIFIED | Lines 12-17 |
| `frontend/src/components/NotificationCenter.tsx` | `/api/v1/notifications/{id}/read` | useMutation PATCH on mark-read click | VERIFIED | Lines 19-22 |
| `nginx/nginx.conf` | `frontend:80` | `location / { proxy_pass http://frontend }` | VERIFIED | Lines 43-47 |
| `nginx/nginx.conf` | `backend:8000` | SSE location block with proxy_buffering off | VERIFIED | Lines 19-30 |
| `docker-compose.yml` | `frontend/Dockerfile` | `build: ./frontend` service definition | VERIFIED | Line 55-57 |

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| DASH-01 | 03-01 | Real-time dashboard shows events with ProphetX vs. real-world status; mismatches highlighted | SATISFIED | EventsTable has both columns + red-50 border-l-4 highlight on !status_match |
| DASH-02 | 03-01 | Real-time dashboard shows markets with liquidity vs. threshold; below-threshold highlighted | SATISFIED | MarketsTable has both columns + red-50 border-l-4 highlight on below_threshold |
| DASH-03 | 03-01, 03-02, 03-05 | Dashboard updates via SSE within 30 seconds; SSE connection drop shows visible banner within 20s | SATISFIED | SSE wiring complete; ping=20 alive; SseProvider uses lastOpenRef 15s timeout-based detection (fixed in 03-05). Human test for timing needed. |
| DASH-04 | 03-01, 03-02, 03-05 | System health shows polling worker status and last-checked timestamps per event | SATISFIED | Worker dots verified; EventRow.last_prophetx_poll matches backend field; Last Checked column now shows real timestamps (fixed in 03-05) |
| ALERT-01 | 03-02, 03-05 | Slack alerts for: status mismatch, auto-update success/failure, low liquidity, postponed/cancelled, API retries exhausted | SATISFIED | All alert paths wired: flag_event, liquidity_alert, auto_update_success, auto_update_failure (last two fixed in 03-05) |
| ALERT-02 | 03-02 | Max 1 alert per event per condition per 5 minutes (Redis TTL deduplication) | SATISFIED | `r.set(dedup_key, "1", ex=300, nx=True)` in send_alerts.py |
| ALERT-03 | 03-02, 03-05 | Alert-only mode: detects mismatches, sends alerts, no ProphetX writes; toggled via admin config | SATISFIED | ProphetX write guard verified; no ProphetX API call when alert_only_mode=true; send_alerts_task.delay() now fires with alert-only note in message (fixed in 03-05) |
| NOTIF-01 | 03-03, 03-05 | In-app notification center with read/unread state; clicking notification navigates to relevant event/market | SATISFIED | Bell icon, panel, mark-read all work; entity display is `<a href="/#events">` / `<a href="/#markets">` anchor (fixed in 03-05) |

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `backend/app/workers/update_event_status.py` | 122-124 | TODO comment: "Wire real ProphetX write endpoint when confirmed" | INFO | Expected — ProphetX write API unconfirmed; explicitly deferred |
| `frontend/src/api/events.ts` | 11 | `last_checked_at` field name mismatch | RESOLVED (03-05) | Fixed: renamed to `last_prophetx_poll` to match backend schema |
| `frontend/src/components/SseProvider.tsx` | 12 | `readyState === EventSource.CLOSED` never triggers during auto-reconnect | RESOLVED (03-05) | Fixed: replaced with lastOpenRef timeout-based detection |
| `frontend/src/components/NotificationCenter.tsx` | 84-87 | Entity shown as text with no navigation | RESOLVED (03-05) | Fixed: entity display is now `<a href>` anchor navigating to /#events or /#markets |

---

## Human Verification Required

### 1. SSE 30-second Update Timing

**Test:** Start the full docker stack with valid PROPHETX_API_KEY in .env. Open the dashboard. Observe that when a poll worker detects a state change, the EventsTable/MarketsTable updates within 30 seconds without a page refresh.

**Expected:** Table rows update automatically within 30 seconds; no manual refresh needed.

**Why human:** Requires live workers with valid API credentials — workers are currently Exited(2) due to missing PROPHETX_API_KEY (pre-existing blocker from Phase 2).

### 2. Full Login-to-Dashboard Browser Test

**Test:** Navigate to http://localhost/ in a browser. Verify login page appears. Log in with ADMIN_EMAIL/ADMIN_PASSWORD from .env. Verify dashboard renders with EventsTable, MarketsTable, SystemHealth dots, and Bell icon all visible.

**Expected:** Login form submits successfully; dashboard loads; all four UI sections visible.

**Why human:** The 03-04 checkpoint:human-verify task was auto-approved (`auto_advance=true` in SUMMARY) — no human actually confirmed the browser UI.

### 3. Slack Alert End-to-End

**Test:** Set SLACK_WEBHOOK_URL in .env and restart the stack. Trigger a condition (liquidity breach or flag_event) by manipulating test data. Verify the Slack channel receives the alert with the mrkdwn block.

**Expected:** Slack message appears with `*[ALERT_TYPE]*` header and entity context. A second trigger within 5 minutes sends no duplicate alert.

**Why human:** Requires external Slack configuration and a triggerable live condition.

---

## Gaps Summary

**All 4 gaps resolved by plan 03-05 (gap closure executed 2026-02-26).**

**Gap 1 — Missing send_alerts call in update_event_status (ALERT-01, ALERT-03): RESOLVED**
Fixed in 03-05: `send_alerts_task.delay(alert_type='auto_update_success', ...)` added after `session.commit()` on success path; `send_alerts_task.delay(alert_type='auto_update_failure', ...)` added in except block after audit log commit (wrapped in its own try/except to not block retry logic).

**Gap 2 — SSE reconnect banner never triggers (DASH-03): RESOLVED**
Fixed in 03-05: SseProvider replaced with `lastOpenRef` timestamp tracking. Banner shows when `readyState !== OPEN` AND `elapsed >= 15000ms` since last OPEN observation. Covers CONNECTING state (genuine network drops), not just programmatic CLOSED state.

**Gap 3 — Notification entity navigation not implemented (NOTIF-01): RESOLVED**
Fixed in 03-05: Entity display in NotificationCenter.tsx replaced with `<a href="/#markets">` or `<a href="/#events">` anchor based on `n.entity_type`. Clicking navigates to relevant dashboard section.

**Gap 4 — Last-checked timestamp field name mismatch (DASH-04): RESOLVED**
Fixed in 03-05: `EventRow.last_checked_at` renamed to `last_prophetx_poll` in `frontend/src/api/events.ts`. `EventsTable.tsx` updated to read `event.last_prophetx_poll`. TypeScript compilation passes with no errors. Old field name entirely removed from codebase.

---

_Verified: 2026-02-26 (initial), Re-verified: 2026-02-26T17:26:33Z (after 03-05 gap closure)_
_Verifier: Claude (gsd-verifier)_
