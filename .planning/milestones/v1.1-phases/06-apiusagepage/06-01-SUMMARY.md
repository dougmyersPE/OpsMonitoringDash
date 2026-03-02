---
phase: 06-apiusagepage
plan: 01
status: complete
started: 2026-03-02
completed: 2026-03-02
requirements_completed: [USAGE-02, USAGE-03, USAGE-04]
---

# Plan 06-01 Summary: Backend Data Pipeline

## What Was Built
Complete backend data pipeline for the API Usage page:
1. Quota header capture in Odds API client (x-requests-remaining/used) and Sports API client (x-ratelimit-requests-remaining/limit per sport family) — stored in Redis with 25h TTL
2. ApiUsageSnapshot model + Alembic migration 006 for persistent 7-day call volume history
3. Nightly rollup worker (02:00 UTC crontab) that persists yesterday's Redis counters to PostgreSQL
4. Extended GET /api/v1/usage endpoint returning: calls_today, 7-day history (DB + today from Redis), quota (Odds API + Sports API per-sport), intervals (current + minimum), and projections (monthly total + per-worker)

## Key Files

### Created
- `backend/app/models/api_usage_snapshot.py` — SQLAlchemy model with UNIQUE(worker_name, snapshot_date)
- `backend/alembic/versions/006_api_usage_snapshots.py` — DB migration for api_usage_snapshots table
- `backend/app/workers/rollup_api_usage.py` — Nightly rollup worker with idempotent upsert

### Modified
- `backend/app/clients/base.py` — Added _capture_quota_headers() hook to _get() and _post()
- `backend/app/clients/odds_api.py` — Override hook to capture Odds API quota headers to Redis
- `backend/app/clients/sports_api.py` — Capture Sports API quota headers per sport family to Redis
- `backend/app/workers/celery_app.py` — Registered rollup worker + crontab beat schedule entry
- `backend/app/api/v1/usage.py` — Full rewrite: comprehensive usage data endpoint

## Decisions Made
- Quota limit for Odds API comes from system_config (DB-configurable via PATCH /config) rather than being hardcoded — returns null if not configured
- Sports API quota is keyed per sport family (basketball, hockey, etc.) matching api-sports.io's per-sport daily quota model
- Today's data is appended to the history array from live Redis counters, creating a seamless chart experience even before rollup worker runs
- Rollup worker uses INSERT ON CONFLICT UPDATE for idempotency — safe to re-run

## Self-Check: PASSED
- [x] All files parse without syntax errors
- [x] BaseAPIClient has _capture_quota_headers hook
- [x] Odds API client captures quota headers to Redis
- [x] Sports API client captures per-sport quota headers to Redis
- [x] ApiUsageSnapshot model exists with correct schema
- [x] Alembic migration 006 creates table with unique constraint + date index
- [x] Rollup worker registered in celery_app with crontab schedule
- [x] Usage endpoint returns all 5 data sections
