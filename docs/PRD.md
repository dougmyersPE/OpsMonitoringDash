# ProphetX Market Monitor - Product Requirements Document

**Document Version:** 1.0
**Last Updated:** 2026-02-24
**Status:** Draft
**Owner:** Doug

---

## Executive Summary

**TL;DR:** An internal operations dashboard that continuously monitors ProphetX prediction market events and markets, automatically syncs event statuses with real-world sports outcomes, and alerts the team when markets fall below liquidity thresholds or when automated actions succeed or fail.

**Problem Statement:** As a prediction market operator on ProphetX, keeping event statuses synchronized with real-world game states (scheduled → live → ended → cancelled) is a manual, error-prone process. Markets that lag behind real-world status confuse bettors and create operational risk. Additionally, markets with insufficient liquidity provide poor user experience and reduce platform engagement.

**Proposed Solution:** A background monitoring service paired with a real-time operations dashboard that polls ProphetX and external sports data sources every ~30 seconds, detects status mismatches and liquidity shortfalls, automatically corrects event statuses, and alerts the team via Slack and in-app notifications when liquidity thresholds are breached or any action requires human attention.

**Success Metrics:**
- Event status mismatch time reduced to < 1 minute from real-world state change
- Zero markets fall below minimum liquidity thresholds without team awareness
- Dashboard reflects current state with < 30 second latency
- 100% of auto-resolvable mismatches corrected without human intervention
- Team alert response time < 5 minutes for critical issues

---

## 1. Product Overview

### 1.1 Vision & Objectives

**Vision:** Give the ProphetX operations team real-time visibility and automated control over the health of all active events and markets, eliminating manual status monitoring and ensuring the platform always reflects real-world conditions.

**Primary Objectives:**
- Automatically keep ProphetX event statuses in sync with real-world game states using SportsDataIO and supplementary data sources
- Monitor market liquidity levels against configurable thresholds and alert the team when markets fall below minimums
- Provide a real-time command-and-control dashboard so operators can see the full health of the platform at a glance
- Alert the team via Slack and in-app notifications when issues are detected or when automated actions succeed or fail

### 1.2 Target Audience

**Primary Users:**
- **Admin (Operator/Owner):** Full system control — configures thresholds, manages users, views all data, can override automated actions
- **Operator:** Can view dashboard, acknowledge alerts, manually trigger status updates or liquidity additions
- **Read-Only Viewer:** Can view dashboard and historical logs; no ability to trigger actions

**Secondary Users/Stakeholders:**
- ProphetX platform end users (indirectly benefit from accurate statuses and liquid markets)

### 1.3 Scope

**In Scope (MVP):**
- ProphetX API integration (event status reads/writes, market liquidity reads)
- SportsDataIO integration for real-world game status (NFL, NBA, MLB, NHL, and other covered sports)
- Supplementary data scraping/APIs for additional validation
- Automated event status synchronization (Upcoming → Live → Ended, with Cancelled handling)
- Liquidity monitoring with configurable per-market thresholds and alerting when breached
- Real-time dashboard with live status of all events and markets
- Slack alerting integration
- In-app notification center
- Audit log of all automated and manual actions
- Role-based access control (Admin, Operator, Read-Only)

**Out of Scope (Future Phases):**
- Automated liquidity top-up (deferred until ProphetX API liquidity mechanics are confirmed)
- Market creation/management
- Automated odds-making or pricing
- Mobile native app (web-responsive dashboard is sufficient for MVP)
- Email or SMS alerting (Slack + in-app covers MVP needs)
- Historical analytics and reporting beyond audit log

**Non-Goals:**
- This system does not manage user accounts or betting activity on ProphetX
- This is not a public-facing product — it is an internal operations tool
- This system does not make market-making or pricing decisions

---

## 2. User Stories & Requirements

### 2.1 Core User Stories

---

**Epic 1: Event Status Monitoring & Synchronization**

**User Story 1.1 — Auto-update event to Live:**
- **Story:** As an operator, I want the system to automatically mark a ProphetX event as "Live" when the real-world game starts, so that bettors see accurate status without manual intervention.
- **Acceptance Criteria:**
  - Given a ProphetX event in "Upcoming" status, when SportsDataIO reports the corresponding game as "InProgress", then the system calls the ProphetX API to update the event status to "Live" within 30 seconds
  - Given the update succeeds, then the action is written to the audit log with timestamp, source data, and result
  - Given the update fails (API error), then a Slack and in-app alert is sent immediately
- **Priority:** Must-Have

**User Story 1.2 — Auto-update event to Ended:**
- **Story:** As an operator, I want the system to automatically mark a ProphetX event as "Ended" when the real-world game concludes, so markets can be settled promptly.
- **Acceptance Criteria:**
  - Given a ProphetX event in "Live" status, when SportsDataIO reports the game as "Final", then the system updates the event to "Ended" within 30 seconds
  - Given the update is applied, then a Slack notification is sent summarizing the event and outcome
- **Priority:** Must-Have

**User Story 1.3 — Cancel markets for postponed/cancelled events:**
- **Story:** As an operator, I want the system to flag or automatically cancel ProphetX markets when the corresponding real-world event is postponed or cancelled, so that bettors are not left in open positions on invalid events.
- **Acceptance Criteria:**
  - Given a real-world game status of "Postponed" or "Canceled" from SportsDataIO, when the system detects this, then it sends an immediate Slack and in-app alert flagging the event
  - Given the ProphetX API supports market cancellation, the system may optionally auto-cancel with admin approval setting
  - Given the alert is sent, the event is highlighted in the dashboard as requiring action
- **Priority:** Must-Have

**User Story 1.4 — Dashboard mismatch view:**
- **Story:** As an operator, I want to see a real-time dashboard showing all events with their ProphetX status and real-world status side-by-side, with mismatches highlighted prominently.
- **Acceptance Criteria:**
  - Given any active event, the dashboard shows: event name, sport/league, ProphetX status, real-world status, last checked timestamp, and a match/mismatch indicator
  - Given a status mismatch exists, the row is highlighted in a distinct warning color
  - Given auto-resolution is in progress, the row shows a "Resolving..." state
  - Dashboard updates within 30 seconds of any status change
- **Priority:** Must-Have

---

**Epic 2: Liquidity Monitoring & Management**

**User Story 2.1 — Detect low liquidity:**
- **Story:** As an operator, I want the system to detect when a market's liquidity falls below my configured threshold, so I can take action before the market becomes non-functional.
- **Acceptance Criteria:**
  - Given a market's current liquidity drops below the configured minimum threshold, the system triggers an alert within one polling cycle (≤ 30 seconds)
  - The alert includes: market name, event name, current liquidity, and configured threshold
  - The dashboard highlights the market as "Low Liquidity"
- **Priority:** Must-Have

**User Story 2.2 — Configure liquidity thresholds:**
- **Story:** As an admin, I want to configure minimum liquidity thresholds per market (or globally as a default), so I can tune alert sensitivity to each market's needs.
- **Acceptance Criteria:**
  - Given I am an Admin, I can set a minimum liquidity threshold per market
  - Given no per-market setting exists, the system uses the global default threshold
  - Settings changes are recorded in the audit log
- **Priority:** Must-Have

---

**Epic 3: Alerting & Notifications**

**User Story 3.1 — Slack alerts for critical issues:**
- **Story:** As an operator, I want to receive Slack messages when status mismatches or liquidity issues are detected (or when auto-resolution occurs), so I'm always aware of platform health.
- **Acceptance Criteria:**
  - Given a status mismatch is detected, a Slack message is sent to the configured channel within one polling cycle
  - Given a market's liquidity falls below its threshold, a Slack alert is sent with current and threshold values
  - Given an auto-status-update is completed or fails, a Slack notification is sent with the result
  - Slack messages include relevant context: event name, market name, type of issue, timestamps
- **Priority:** Must-Have

**User Story 3.2 — In-app notification center:**
- **Story:** As an operator, I want to see a notification center in the dashboard showing recent alerts and actions, so I have a log of what the system has done and what requires attention.
- **Acceptance Criteria:**
  - The dashboard has a notification bell/panel listing recent alerts and automated actions
  - Unread notifications are visually distinct from read ones
  - Clicking a notification navigates to the relevant event or market
  - Notifications can be marked as acknowledged
- **Priority:** Must-Have

---

**Epic 4: Audit Log & History**

**User Story 4.1 — Full audit trail:**
- **Story:** As an admin, I want a complete log of every automated and manual action the system takes, so I can audit activity, debug issues, and understand historical behavior.
- **Acceptance Criteria:**
  - Every status update, alert sent, and configuration change is written to the audit log with: timestamp, action type, actor (system or user), before/after state, and result
  - The audit log is searchable and filterable by date range, action type, event, and actor
  - Audit log entries cannot be deleted
- **Priority:** Must-Have

---

**Epic 5: User Management & Access Control**

**User Story 5.1 — Role-based access:**
- **Story:** As an admin, I want to invite team members and assign them roles so I can control who can view vs. take actions in the system.
- **Acceptance Criteria:**
  - Admin can create user accounts and assign roles: Admin, Operator, Read-Only
  - Admin role: full access to configuration, user management, and all actions
  - Operator role: can view dashboard, acknowledge alerts, manually trigger updates
  - Read-Only role: can view dashboard and logs only
  - Role changes take effect immediately
- **Priority:** Must-Have

---

### 2.2 Non-Functional Requirements

**Performance:**
- Dashboard load time: < 2 seconds on initial load
- Real-time update latency: < 30 seconds from source change to dashboard display
- API polling cycle: every 15–30 seconds (configurable per data source)
- System handles 100+ concurrent events and markets without degradation

**Security:**
- Authentication: Email/password with session tokens (JWT)
- Authorization: Role-based access control enforced server-side
- All ProphetX API credentials and SportsDataIO API keys stored as encrypted environment variables, never in code
- HTTPS enforced for all connections
- Audit log is append-only (no delete capability)

**Reliability:**
- Background polling workers must restart automatically if they crash (process supervisor or container restart policy)
- Failed ProphetX API calls retry with exponential backoff (3 retries max)
- System should be fault-tolerant to SportsDataIO outages — log the error, alert the team, but do not crash

**Scalability:**
- Designed to support up to 500 concurrent events and 1,000 markets without architectural changes
- Polling workers should be horizontally scalable (add more workers to reduce per-worker load)

---

## 3. Technical Specifications

### 3.1 Recommended Tech Stack

**Backend:**
- Language/Framework: **Python 3.11+ with FastAPI** — async-native, ideal for concurrent API polling, excellent REST API support
- Task Queue: **Celery with Redis** — handles scheduled polling tasks, retries, and background workers
- Rationale: Python has the best ecosystem for sports data integrations, async FastAPI supports concurrent polling efficiently, and Celery is the industry standard for periodic background tasks

**Frontend:**
- Framework: **React 18 + TypeScript**
- Styling: **Tailwind CSS + shadcn/ui** — fast to build professional-looking dashboards
- Real-time: **Server-Sent Events (SSE)** for pushing dashboard updates from backend to browser
- State Management: **React Query (TanStack Query)** — handles data fetching, caching, and real-time sync well

**Database:**
- Primary: **PostgreSQL** — structured relational data for events, markets, audit log, users, config
- Cache/Queue: **Redis** — Celery task broker, caching current event/market states for fast dashboard reads, SSE pub/sub
- Rationale: PostgreSQL for durability and queryability of historical data; Redis for high-frequency state that drives the real-time dashboard

**Infrastructure:**
- Containerization: **Docker + Docker Compose** — consistent deployment, easy to run on any VPS or cloud instance
- Hosting: **VPS or cloud VM** (DigitalOcean Droplet, AWS EC2, or Hetzner) with Docker Compose
- Reverse Proxy: **Nginx** — serves frontend, proxies backend, handles SSL termination
- SSL: **Let's Encrypt / Certbot** — free SSL certificates
- Process Management: Docker container restart policies for worker resilience

### 3.2 Data Models

**Entity: Event**
```
{
  id: UUID (primary key, auto-generated)
  prophetx_event_id: string (required, unique — ProphetX's internal ID)
  sport: string (e.g., "NFL", "NBA", "MLB")
  league: string
  name: string (e.g., "Kansas City Chiefs vs. Philadelphia Eagles")
  scheduled_start: timestamp
  prophetx_status: enum [verify exact values from ProphetX API docs — likely "upcoming", "live", "ended", "cancelled", "suspended" or similar]
  real_world_status: enum ["scheduled", "in_progress", "final", "postponed", "cancelled", "unknown"]
  status_match: boolean (computed: do prophetx_status and real_world_status correspond?)
  last_prophetx_poll: timestamp
  last_real_world_poll: timestamp
  external_event_id: string (SportsDataIO game ID)
  created_at: timestamp
  updated_at: timestamp
}
```

**Entity: Market**
```
{
  id: UUID (primary key, auto-generated)
  prophetx_market_id: string (required, unique)
  event_id: UUID (foreign key → Event)
  name: string (e.g., "Will the Chiefs win?")
  current_liquidity: decimal (current total liquidity in USD)
  min_liquidity_threshold: decimal (nullable — falls back to global default)
  status: enum ["active", "suspended", "settled", "cancelled"]
  last_polled: timestamp
  created_at: timestamp
  updated_at: timestamp
}
```

**Entity: AuditLog**
```
{
  id: UUID (primary key, auto-generated)
  timestamp: timestamp (required, indexed)
  action_type: enum ["status_update", "alert_sent", "config_change", "manual_override"]
  actor: string ("system" or user_id)
  entity_type: enum ["event", "market", "user", "config"]
  entity_id: UUID
  before_state: json (nullable)
  after_state: json (nullable)
  result: enum ["success", "failure", "pending"]
  error_message: string (nullable)
  metadata: json (nullable — extra context)
}
```

**Entity: User**
```
{
  id: UUID (primary key, auto-generated)
  email: string (required, unique)
  password_hash: string (bcrypt)
  role: enum ["admin", "operator", "readonly"]
  name: string
  is_active: boolean
  created_at: timestamp
  last_login: timestamp
}
```

**Entity: SystemConfig**
```
{
  id: UUID (primary key, auto-generated)
  key: string (unique — e.g., "default_min_liquidity", "polling_interval_seconds", "slack_webhook_url")
  value: string
  description: string
  updated_by: UUID (foreign key → User)
  updated_at: timestamp
}
```

**Entity: Notification**
```
{
  id: UUID (primary key, auto-generated)
  type: enum ["status_mismatch", "status_updated", "low_liquidity", "action_failed", "cancellation_detected"]
  severity: enum ["info", "warning", "critical"]
  title: string
  message: string
  entity_type: enum ["event", "market"]
  entity_id: UUID
  is_read: boolean (default: false)
  created_at: timestamp
}
```

### 3.3 API Specifications

**GET /api/v1/events**
- **Purpose:** List all monitored events with current status
- **Authentication:** Required (JWT)
- **Query Params:** `status`, `sport`, `mismatch_only=true`, `page`, `per_page`
- **Response (200):**
  ```json
  {
    "data": [
      {
        "id": "uuid",
        "name": "Chiefs vs Eagles",
        "sport": "NFL",
        "prophetx_status": "upcoming",
        "real_world_status": "in_progress",
        "status_match": false,
        "last_checked": "2026-02-24T15:30:00Z"
      }
    ],
    "total": 42,
    "page": 1
  }
  ```

**POST /api/v1/events/{id}/sync-status**
- **Purpose:** Manually trigger a status sync for a specific event
- **Authentication:** Required (Operator or Admin role)
- **Response (200):** Updated event object with action result

**GET /api/v1/markets**
- **Purpose:** List all monitored markets with liquidity data
- **Authentication:** Required (JWT)
- **Query Params:** `event_id`, `low_liquidity_only=true`, `page`, `per_page`

**PATCH /api/v1/markets/{id}/config**
- **Purpose:** Update liquidity threshold for a market
- **Authentication:** Required (Admin role)
- **Request Body:** `{ "min_liquidity_threshold": 500 }`

**GET /api/v1/audit-log**
- **Purpose:** Retrieve paginated audit log
- **Authentication:** Required (Operator or Admin role)
- **Query Params:** `from_date`, `to_date`, `action_type`, `entity_id`

**GET /api/v1/notifications**
- **Purpose:** Get current user's unread notifications
- **Authentication:** Required (JWT)

**GET /api/v1/stream**
- **Purpose:** Server-Sent Events stream for real-time dashboard updates
- **Authentication:** Required (JWT via query param)
- **Response:** SSE stream emitting `event_updated`, `market_updated`, `notification` events

**GET /api/v1/config**
**PATCH /api/v1/config**
- **Purpose:** Read and update system configuration (Admin only)

### 3.4 Third-Party Integrations

**Integration 1: ProphetX API**
- **Purpose:** Source of truth for ProphetX event and market data; target for all status updates and liquidity actions
- **Authentication:** API key (Bearer token or as configured by ProphetX)
- **Key Operations:**
  - `GET /events` — fetch all events and their current statuses
  - `PATCH /events/{id}` — update event status
  - `GET /markets` — fetch markets with liquidity data
  - `POST /markets/{id}/cancel` — cancel a market (for postponed/cancelled events)
- **Polling Strategy:** Full event/market list pulled every 30 seconds; individual event updates triggered immediately on detection of mismatch
- **Error Handling:** Exponential backoff (1s, 2s, 4s), max 3 retries; alert team on persistent failure

**Integration 2: SportsDataIO**
- **Purpose:** Real-world sports event status data (game scheduled, in-progress, final, postponed, cancelled)
- **Authentication:** API key (query parameter `key=`)
- **Sports Covered:** NFL, NBA, MLB, NHL, NCAAF, NCAAB, Soccer, Golf, Tennis (varies by subscription tier)
- **Key Endpoints (varies by sport):**
  - `GET /v3/{sport}/scores/json/GamesByDate/{date}` — get all games for a date with current status
  - Status values: `Scheduled`, `InProgress`, `Final`, `F/OT`, `Postponed`, `Canceled`, `Suspended`
- **Polling Strategy:** All scheduled/in-progress games polled every 30 seconds; completed games polled once to confirm final status
- **Cost:** Subscription-based; existing access via Doug's current account

**Integration 3: Supplementary Sports Data Sources**
- **Purpose:** Cross-validation and coverage for sports/events not covered by SportsDataIO
- **Options (to be evaluated):**
  - **The Odds API** (free tier: 500 req/month) — event status and scores for major sports
  - **ESPN Hidden API** (unofficial, free) — real-time scores, use cautiously as it may break
  - **Web scraping** (BeautifulSoup/Playwright) — targeted scraping of sports reference sites as fallback
- **Strategy:** SportsDataIO is primary source; supplementary sources used only when SportsDataIO lacks coverage for a specific event
- **Implementation:** Pluggable data source architecture so new sources can be added without core changes

**Integration 4: Slack**
- **Purpose:** Real-time alerts to operations team
- **Method:** Incoming Webhook URL (configured in SystemConfig)
- **Alert Types:** Status mismatch detected, status auto-updated, cancellation detected, liquidity low, auto-action failed
- **Message Format:** Structured Slack Block Kit messages with event name, type, severity, and action taken
- **Rate Limiting:** Max 1 alert per event per minute to prevent alert fatigue; digest mode for bulk changes

### 3.5 System Architecture

**High-Level Architecture:**
```
[SportsDataIO API]    [ProphetX API]
        ↓                    ↕
  [Polling Workers (Celery)]
        ↓ writes state
  [Redis Cache] ←→ [PostgreSQL DB]
        ↓ pub/sub
  [FastAPI Backend]
        ↓              ↓
  [SSE Stream]    [Slack Webhook]
        ↓
  [React Dashboard]
```

**Key Components:**

- **Polling Workers (Celery Beat + Workers):** Two main tasks run on a ~30-second schedule:
  1. `poll_sports_data` — fetches real-world game statuses from SportsDataIO and supplementary sources
  2. `poll_prophetx` — fetches current event statuses and market liquidity from ProphetX
  Both tasks write results to PostgreSQL and update Redis cache. When a mismatch or threshold breach is detected, they enqueue an action task immediately.

- **Action Workers:** Separate Celery workers handle:
  - `update_event_status` — calls ProphetX API to update event status
  - `send_slack_alert` — sends Slack notification

- **FastAPI Backend:** Serves the REST API, handles authentication/authorization, exposes the SSE endpoint. Reads primarily from Redis cache for speed; writes go to PostgreSQL.

- **Redis:** Serves dual purpose as Celery message broker and as a fast cache for the current state of all events/markets. The SSE endpoint subscribes to Redis pub/sub channels for real-time push to the browser.

- **React Dashboard:** Single-page app connecting to the SSE stream for real-time updates. Displays event status table, market liquidity table, notification panel, and admin configuration views.

**Data Flow (Status Mismatch):**
1. Celery Beat triggers `poll_sports_data` every 30 seconds
2. SportsDataIO returns game as "InProgress"; Redis shows ProphetX event as "upcoming"
3. Worker detects mismatch → enqueues `update_event_status` task immediately
4. Action worker calls ProphetX API → event updated to "live"
5. Worker writes audit log entry to PostgreSQL
6. Worker publishes `event_updated` message to Redis pub/sub
7. FastAPI SSE endpoint pushes update to all connected browsers
8. Dashboard row updates in real-time; notification created; Slack alert sent

---

## 4. User Experience & Design

### 4.1 Design Principles

- **Clarity First:** Operators need to assess platform health at a glance. Critical issues must be immediately visible without scrolling or digging.
- **Actionable Alerts:** Every alert should tell the operator exactly what happened and what they can do about it.
- **Trust Through Transparency:** Show operators what the system is doing automatically (audit log visible from dashboard), so they always know what actions have been taken.

### 4.2 Key User Flows

**Flow 1: Operator Opens Dashboard**
1. Operator logs in and lands on the main dashboard
2. Dashboard shows two primary panels: Events Table and Markets Table
3. Events Table shows all active events, sorted by start time, with ProphetX status vs. real-world status
4. Any mismatched rows are visually highlighted (amber/red depending on severity)
5. Markets Table shows all active markets with current liquidity vs. threshold
6. Markets below threshold are highlighted with a warning indicator
7. Notification bell in the header shows unread alert count

**Flow 2: Automated Status Mismatch Resolution**
1. System detects game has started in real life (SportsDataIO: "InProgress")
2. ProphetX event still shows "upcoming"
3. System immediately enqueues status update
4. Dashboard row for the event turns amber with "Resolving..." badge
5. Update succeeds → row turns green briefly, then normal
6. Slack message posted: "✅ Event 'Chiefs vs Eagles' updated to Live on ProphetX"
7. Notification appears in in-app notification center

**Flow 3: Admin Configures Liquidity Threshold**
1. Admin navigates to a specific market in the Markets Table
2. Clicks "Configure" button
3. Modal shows current min threshold and current liquidity level
4. Admin updates the threshold and saves
5. System immediately begins monitoring against the new threshold
6. Audit log records the change

**Flow 4: Critical Alert (Auto-Resolution Fails)**
1. System attempts to update a stale event status on ProphetX
2. ProphetX API returns an error after 3 retries
3. Dashboard row turns red with "Action Failed" badge
4. Urgent Slack message sent: "🚨 Failed to update 'Chiefs vs Eagles' to Ended after 3 attempts. Manual action required."
5. Operator sees the alert, investigates, and manually resolves from dashboard

### 4.3 UI/UX Requirements

- **Responsive:** Optimized for desktop (1280px+); tablet support (768px+) as secondary
- **Real-time indicators:** Mismatch rows pulsate gently; resolving states show spinners; "Last updated X seconds ago" counter on each table
- **Color coding:** Green = healthy/matched, Amber = warning/mismatch detected, Red = error/action failed, Blue = informational/auto-action in progress
- **Loading states:** Skeleton loaders on initial dashboard load; inline spinners for in-progress actions
- **Empty states:** Clear message when no mismatches/low liquidity markets exist ("All systems healthy")
- **Error states:** Inline error messages with retry button for failed manual actions

---

## 5. Implementation Plan

### 5.1 Development Phases

**Phase 1: Foundation & Core Infrastructure (Week 1–2)**
- Set up project structure: FastAPI backend, React frontend, PostgreSQL, Redis
- Docker Compose configuration for local dev and production
- Database schema and migrations (Alembic)
- User authentication system (JWT)
- ProphetX API client (authenticated, with retry logic)
- SportsDataIO API client
- Celery setup with basic scheduled tasks
- **Deliverables:** Running local environment, auth working, API clients tested

**Phase 2: Monitoring Engine (Week 2–3)**
- Event polling worker (ProphetX + SportsDataIO)
- Status comparison logic and mismatch detection
- Event status auto-update action
- Liquidity polling worker
- Liquidity threshold comparison and alert triggering
- Audit log writes for all actions
- **Deliverables:** Background workers correctly detecting and resolving status mismatches; liquidity alerts firing correctly in test environment

**Phase 3: Dashboard & Real-time UI (Week 3–4)**
- React app scaffolding
- Events Table with status columns and mismatch highlighting
- Markets Table with liquidity levels and threshold indicators
- SSE integration for real-time updates
- Notification center / bell component
- Basic admin config panel (liquidity thresholds)
- **Deliverables:** Fully functional real-time dashboard

**Phase 4: Alerting & User Management (Week 4–5)**
- Slack webhook integration + alert message formatting
- In-app notification creation and read/unread state
- User management (invite, assign roles, deactivate)
- Audit log viewer with search/filter
- **Deliverables:** Full alerting pipeline; multi-user access working

**Phase 5: Supplementary Data Sources & Polish (Week 5–6)**
- Add The Odds API or other supplementary source as fallback
- Alert deduplication / rate limiting (prevent alert spam)
- Dashboard polish: loading states, error states, empty states
- Production deployment (Docker on VPS, Nginx, SSL)
- End-to-end testing with real ProphetX and SportsDataIO data
- **Deliverables:** Production-ready deployment

### 5.2 Task Dependencies

```
[Phase 1: Foundation]
        ↓
[Phase 2: Monitoring Engine] ← requires ProphetX + SportsDataIO clients
        ↓
[Phase 3: Dashboard] ← requires SSE endpoint from backend
[Phase 4: Alerting]  ← can run in parallel with Phase 3
        ↓
[Phase 5: Polish + Deploy]
```

### 5.3 Resource Requirements

**Development Team:**
- 1 Full-stack developer (or Claude Code agent)

**Tools & Services:**
- SportsDataIO: existing subscription (Doug's account)
- ProphetX API: existing credentials
- VPS/Cloud VM: ~$10–20/month (DigitalOcean Droplet or Hetzner)
- Redis: self-hosted in Docker (no extra cost)
- PostgreSQL: self-hosted in Docker (no extra cost)
- Slack: existing workspace
- SSL: Let's Encrypt (free)
- The Odds API (optional supplementary): free tier (500 req/month) or $10/month paid

**Estimated Total Infrastructure Cost:** ~$15–30/month

---

## 6. Testing Strategy

### 6.1 Testing Types

**Unit Testing:**
- Coverage target: 80%
- Key areas: status comparison logic, liquidity threshold evaluation, API client retry logic, data model validation

**Integration Testing:**
- ProphetX API client with mock server (verify auth, retry behavior, correct endpoints)
- SportsDataIO client with mock responses
- Database read/write for all models
- Celery task execution and result handling

**End-to-End Testing:**
- Full mismatch detection → auto-update → dashboard update flow
- Low liquidity detection → Slack alert → dashboard highlight flow
- Manual status sync via dashboard
- Slack notification delivery

### 6.2 Key Test Scenarios

**Scenario 1: Status Mismatch Detection**
- **Given:** ProphetX event status is "upcoming", SportsDataIO returns "InProgress"
- **When:** Polling worker runs
- **Then:** Mismatch is detected, auto-update enqueued within the same polling cycle

**Scenario 2: Successful Auto-Update**
- **Given:** Mismatch detected, ProphetX API is available
- **When:** Action worker runs
- **Then:** ProphetX event is updated to "live", audit log written, Slack alert sent

**Scenario 3: ProphetX API Failure**
- **Given:** Auto-update is attempted, ProphetX API returns 500
- **When:** Retry logic runs (3 attempts with backoff)
- **Then:** After 3 failures, urgent alert sent to Slack and in-app, dashboard shows "Action Failed"

**Scenario 4: Liquidity Below Threshold**
- **Given:** Market's current liquidity is $200, threshold is $500
- **When:** Liquidity polling worker runs
- **Then:** Slack alert sent with market name, current liquidity, and threshold; dashboard highlights market as "Low Liquidity"; notification created in-app

---

## 7. Success Metrics & Analytics

### 7.1 Key Performance Indicators

**Operational Metrics:**
- Mean time to status correction: target < 1 minute from real-world state change
- Liquidity breach incidents: target < 5 per week after system is live
- Auto-resolution rate: % of detected status mismatches corrected without human intervention (target: > 90%)
- Alert false positive rate: target < 5%

**System Health Metrics:**
- Polling worker uptime: > 99.5%
- ProphetX API success rate: monitor and alert if < 98%
- Dashboard SSE connection stability: < 1 disconnect per hour per client

### 7.2 Monitoring

- Application logs: structured JSON logs from all workers and API
- Error tracking: Sentry (free tier) for exception capture and alerting
- Uptime monitoring: simple HTTP health check endpoint; monitored by UptimeRobot (free)

---

## 8. Risk Assessment

### 8.1 Technical Risks

**Risk 1: ProphetX API rate limits or instability**
- **Probability:** Medium
- **Impact:** High — polling and auto-updates depend on this
- **Mitigation:** Implement exponential backoff and circuit breaker; cache last-known state so dashboard continues showing data even if API is temporarily down; alert team if ProphetX API success rate drops below 98%

**Risk 2: SportsDataIO coverage gaps**
- **Probability:** Medium — some niche sports/leagues may not be covered
- **Impact:** Medium — those specific events won't have automated status sync
- **Mitigation:** Pluggable data source architecture allows supplementary sources to fill gaps; dashboard shows "Unknown" for events where real-world status cannot be determined

**Risk 3: Event ID mapping between ProphetX and SportsDataIO**
- **Probability:** High — these two systems use different identifiers and names for the same games
- **Impact:** High — mismatched IDs mean mismatched status comparisons
- **Mitigation:** Build a robust event matching layer using sport type, team names, and scheduled start time; allow manual override/correction of mappings from the admin dashboard

### 8.2 Business Risks

**Risk 1: ProphetX API changes break integration**
- **Probability:** Low-Medium
- **Impact:** High
- **Mitigation:** Abstract all ProphetX API calls behind an internal client class; version pin API interactions; monitor for breaking changes

---

## 9. Launch Plan

### 9.1 Go-Live Checklist

- [ ] All acceptance criteria for Must-Have user stories met
- [ ] ProphetX API credentials configured and tested in production
- [ ] SportsDataIO API key configured and tested in production
- [ ] Slack webhook configured and tested
- [ ] Database migrations applied to production PostgreSQL
- [ ] Admin user account created
- [ ] Liquidity alert thresholds configured for all active markets
- [ ] Docker Compose running stably on VPS with restart policies
- [ ] Nginx + SSL configured and HTTPS working
- [ ] Celery workers confirmed running and polling successfully
- [ ] Dashboard loading and SSE stream stable
- [ ] Audit log writing confirmed for automated actions
- [ ] Rollback plan: `docker compose down` + restore last DB backup

### 9.2 Rollout Strategy

- **Initial Testing:** Run system in "alert-only" mode (no auto-updates) for 48 hours to validate mismatch detection accuracy
- **Soft Launch:** Enable auto-updates for a subset of events; monitor closely for 1 week
- **Full Launch:** Enable auto-updates for all markets; liquidity monitoring active for all markets

---

## 10. Future Roadmap

### 10.1 Phase 2 Features (1–3 months post-launch)

- Email digest / daily summary report of platform health
- Automated liquidity top-up via ProphetX API (once API mechanics are confirmed)
- Historical analytics: trend charts for liquidity levels over time, mismatch frequency by sport
- Market performance dashboard: volume, open interest, settlement history
- Configurable alert escalation (e.g., if no acknowledgement within 10 minutes, escalate to a different Slack channel)
- Additional data source integrations (Sportradar, ESPN API)

### 10.2 Long-term Vision (3–6 months)

- Automated event ingestion: discover new ProphetX events automatically and begin monitoring without manual setup
- Predictive liquidity management: ML-based model that predicts when liquidity will drop based on event timing and market activity patterns
- Multi-platform support: extend monitoring to other prediction market platforms
- Mobile-responsive redesign for tablet use during live sporting events

---

## 11. Appendix

### 11.1 Glossary

- **Event:** A real-world occurrence (a sports game) that is represented on ProphetX as something users can bet on
- **Market:** A specific betting question within an event (e.g., "Will Team A win?")
- **Liquidity:** The amount of capital available on both sides of a market for bets to be matched against
- **Status Mismatch:** When a ProphetX event's status does not correspond to the event's real-world status
- **Polling Cycle:** One execution of the background worker that checks ProphetX and SportsDataIO for updates

### 11.2 References

- ProphetX API Documentation: (provide URL or internal docs link)
- SportsDataIO Developer Documentation: https://sportsdata.io/developers
- The Odds API Documentation: https://the-odds-api.com/liveapi/guides/v4/ (supplementary source)

### 11.3 Change Log

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-02-24 | Doug | Initial draft |
| 1.1 | 2026-02-24 | Doug | Removed automated liquidity top-up (deferred to future phase); liquidity module is monitor + alert only |
