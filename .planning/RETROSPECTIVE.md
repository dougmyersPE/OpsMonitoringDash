# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v1.0 — MVP

**Shipped:** 2026-02-26
**Phases:** 3 | **Plans:** 11

### What Was Built
- Docker Compose infrastructure (PostgreSQL, Redis/RedBeat, Nginx, Celery)
- JWT auth with 3-role RBAC, 5 poll workers, event ID matching layer
- Real-time SSE dashboard with mismatch/liquidity highlighting
- Slack alerting with deduplication, alert-only mode, in-app notification center
- Append-only audit log

### What Worked
- Strict phase dependency ordering (infra → engine → UI) prevented rework
- RedBeat chosen from day one avoided painful Beat restart issues later
- Alert-only mode shipped before enabling writes — safe rollout

### What Was Inefficient
- ProphetX base URL was wrong initially (placeholder DNS failure)
- SDIO NFL/NCAAB/NCAAF endpoints 404 discovered during execution, not research
- Sports API false-positive alerts shipped and had to be fixed in v1.1

### Patterns Established
- Docker Compose with code baked into images (no bind mounts)
- Redis SETNX for alert deduplication (300s TTL)
- SSE auth via ?token= query param (EventSource limitation)
- Worker heartbeat via Redis key TTL (90s)

### Key Lessons
1. Validate external API endpoints during research, not execution — the SDIO 404s and ProphetX DNS failure cost time
2. Time guard logic needs actual datetime from source, not reconstructed proxies — noon-UTC caused false positives
3. Ship alert-only mode before enabling automated writes — this pattern should persist

### Cost Observations
- Model mix: ~80% opus, ~20% sonnet
- Execution speed: 3 phases in 2 days
- Notable: Phase 3 had 5 plans (most complex) but gap closure plan (03-05) was necessary — future phases should anticipate wiring gaps

---

## Milestone: v1.1 — Stabilization + API Usage

**Shipped:** 2026-03-02
**Phases:** 4 | **Plans:** 7

### What Was Built
- Fixed false-positive alerts (actual game datetimes + 6h threshold)
- Redis INCRBY call counters in all 5 poll workers
- DB-backed poll intervals with bootstrap surviving Beat restarts
- Server-side minimum interval enforcement (HTTP 422)
- Complete API Usage page: quota cards, 7-day chart, projections, admin controls
- Documentation gap closure (VERIFICATION.md, SUMMARY frontmatter, REQUIREMENTS.md)

### What Worked
- Counter foundation (Phase 4) started accumulating data before frontend build (Phase 6) — real data on day one
- DB-backed intervals (Phase 5) before UI (Phase 6) — no race conditions possible
- Milestone audit caught documentation gaps before archival
- Plan execution was fast: 7 plans averaged ~10 min each

### What Was Inefficient
- Phase 6 SUMMARY frontmatter and REQUIREMENTS.md checkboxes weren't updated during execution — required a whole Phase 7 to fix
- Audit found only documentation gaps (no code issues) — suggests over-cautious verification process
- 39 commits for 4 phases seems high — atomic commits are good but documentation commits inflate count

### Patterns Established
- Redis INCRBY counter pattern: `api_calls:{worker}:{YYYY-MM-DD}` with 8-day TTL
- Deferred import pattern for celery_app in API process
- `run_in_executor` for sync RedBeat operations in async handlers
- beat_bootstrap.py reads DB on start, writes RedBeat entries
- Quota header capture via BaseAPIClient hook

### Key Lessons
1. Update SUMMARY frontmatter and REQUIREMENTS.md checkboxes during plan execution, not as a separate phase — Phase 7 was entirely preventable overhead
2. Milestone audit is valuable for catching documentation gaps but should happen earlier (after each phase completion, not just before archival)
3. Backend-before-frontend phasing works well for data pipeline features — Phase 4→5→6 ordering was correct
4. Validation scripts (confidence threshold) that require human judgment should be checkpoint tasks, not automated tests

### Cost Observations
- Model mix: ~70% opus, ~30% sonnet/haiku (balanced profile)
- Sessions: ~5
- Notable: Phase 7 (doc gap closure) was 5 min — minimal cost but shouldn't have been needed

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Phases | Plans | Key Change |
|-----------|--------|-------|------------|
| v1.0 | 3 | 11 | Established foundation; discovered external API issues during execution |
| v1.1 | 4 | 7 | Added milestone audit; found documentation gaps need real-time tracking |

### Top Lessons (Verified Across Milestones)

1. Validate external APIs during research phase — saves rework (v1.0 SDIO 404s, v1.0 ProphetX DNS)
2. Backend-before-frontend ordering prevents rework and provides real data for UI (v1.0 engine→dashboard, v1.1 counters→usage page)
3. Documentation artifacts (VERIFICATION.md, SUMMARY frontmatter, REQUIREMENTS.md checkboxes) should be updated atomically with plan execution, not deferred
