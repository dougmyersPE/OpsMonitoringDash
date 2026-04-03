# Phase 13: Status Processing and Matching - Context

**Gathered:** 2026-04-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Incoming OpticOdds tennis messages are matched to ProphetX events by competitor names + date window, statuses are written to the `opticodds_status` DB column, special tennis statuses (walkover/retired/suspended) trigger Slack alerts, and `compute_status_match` includes OpticOdds as a source for mismatch detection.

Requirements: TNNS-02, TNNS-03, AMQP-03, MISM-01

</domain>

<decisions>
## Implementation Decisions

### Fuzzy Matching Strategy (TNNS-02)
- **D-01:** Mirror `poll_oddsblaze.py` matching pattern — competitor name token overlap + 24h date window. This is the proven pattern used by OddsBlaze and ESPN workers for fuzzy event matching.
- **D-02:** Match logic lives in the consumer's `_on_message` callback path. Parse competitor names from OpticOdds message body, query DB for ProphetX events in the same sport (tennis) within a date window, score by name token overlap, and write to the best match above a threshold.
- **D-03:** When no match is found, log at WARNING level (not an error — could be an event we don't track). Do not create new events from OpticOdds data; only update existing ProphetX events.

### Status Writing (TNNS-01 completion)
- **D-04:** On successful match, write the mapped canonical status from `_OPTICODDS_CANONICAL` to the `opticodds_status` column on the matched event row. Use async DB session from within the consumer (same pattern as `poll_oddsblaze.py` DB writes).
- **D-05:** After writing `opticodds_status`, call `compute_status_match()` and update `status_match` on the same event row — triggers SSE push to dashboard via existing mismatch detection flow.

### Special Status Alerting (TNNS-03)
- **D-06:** `walkover`, `retired`, and `suspended` statuses are written verbatim (raw value) to `opticodds_status` column. They are also mapped through `_OPTICODDS_CANONICAL` for canonical comparison (walkover→ended, retired→ended, suspended→live).
- **D-07:** These three special statuses trigger a Slack alert with event context (event name, teams, raw status) using the existing `SLACK_WEBHOOK_URL` + dedup pattern from Phase 12. Separate from the "unknown status" alert — these are known but operationally significant.

### Redis Key Alignment (AMQP-03)
- **D-08:** Keep `opticodds:connection_state` and `opticodds:last_message_at` prefix from Phase 12 — already deployed, already wired to the `/health/workers` endpoint. AMQP-03 requirement is satisfied by these existing keys. The ROADMAP mentions `rmq:` prefix but Phase 12 implementation used `opticodds:` consistently. No change needed.

### Mismatch Detection Integration (MISM-01)
- **D-09:** Add `opticodds_status: str | None = None` parameter to `compute_status_match()` in `mismatch_detector.py`. Add `_OPTICODDS_CANONICAL` dict to the same file. NULL-safe: when `opticodds_status` is None (non-tennis events), the source is simply skipped — no effect on the match result.
- **D-10:** Also add `opticodds_status` parameter to `compute_is_critical()` following the same pattern. OpticOdds reporting live while ProphetX shows not_started counts toward the 2-source threshold.
- **D-11:** All callers of `compute_status_match` must be updated to pass `opticodds_status` — grep for all call sites and add the parameter. Phase 12 STATE.md already noted: "compute_status_match reduced to 5-param signature — Phase 13 extends to 6-param with opticodds."

### DB Session Pattern
- **D-12:** The consumer needs a synchronous or sync-compatible DB session for writes. Follow the pattern from `poll_oddsblaze.py` — create a DB session per message batch or per-message, write, commit, close. pika's BlockingConnection runs synchronously so use synchronous SQLAlchemy sessions (not async).

### Claude's Discretion
- Exact fuzzy match threshold (0.5-0.9 range — look at what poll_oddsblaze uses and match it)
- DB session lifecycle details (per-message vs batched)
- Logging verbosity for match hits/misses
- Test structure for fuzzy matching unit tests

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Fuzzy Matching Pattern (primary analogue)
- `backend/app/workers/poll_oddsblaze.py` — Fuzzy-match pattern by team names + date window, source column write, `compute_status_match()` call, SSE publish
- `backend/app/workers/poll_espn.py` — Alternative fuzzy match approach for tennis/MMA (competitor names + date)

### Consumer Module (modify in this phase)
- `backend/app/workers/opticodds_consumer.py` — Phase 12 consumer; `_on_message()` callback needs DB write + match logic added

### Mismatch Detection (modify in this phase)
- `backend/app/monitoring/mismatch_detector.py` — `compute_status_match()` and `compute_is_critical()` signatures; `_ODDSBLAZE_CANONICAL` dict pattern; add `_OPTICODDS_CANONICAL` and `opticodds_status` parameter

### DB and Models
- `backend/app/models/event.py` — Event model with `opticodds_status` column (already added in Phase 12)
- `backend/app/db/session.py` — DB session factory

### Health Keys (already deployed)
- `backend/app/api/v1/health.py` — `/health/workers` already reads `opticodds:connection_state` keys (Phase 12)

### Requirements
- `.planning/REQUIREMENTS.md` §Tennis Status Integration — TNNS-02 (fuzzy match), TNNS-03 (special statuses)
- `.planning/REQUIREMENTS.md` §AMQP Consumer Infrastructure — AMQP-03 (Redis connection state keys)
- `.planning/REQUIREMENTS.md` §Mismatch Detection — MISM-01 (OpticOdds in compute_status_match)

### Research
- `.planning/research/SUMMARY.md` — Full research summary with OpticOdds message schema (MEDIUM confidence)
- `.planning/research/FEATURES.md` — P1/P2 feature breakdown with phase mapping

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `poll_oddsblaze.py` — Complete fuzzy match + DB write + status_match recompute pattern. Direct template for the OpticOdds integration.
- `mismatch_detector.py` — `_ODDSBLAZE_CANONICAL` dict and `compute_status_match()` with 5 source params. Extend to 6.
- `opticodds_consumer.py` — Phase 12 consumer with `_on_message()`, `_OPTICODDS_CANONICAL`, Slack alerting. Modify to add DB writes.
- `_alert_unknown_status()` in consumer — Slack + Redis dedup pattern reusable for special status alerts (D-07).

### Established Patterns
- Fuzzy matching: team name tokenization, overlap scoring, date window filtering (24h)
- Status canonical mapping: per-source dict mapping raw values to `scheduled/inprogress/final`
- `compute_status_match()` call pattern: called after every source status write, result stored on event row
- SSE push: triggered automatically when `status_match` changes (existing mismatch detection flow)

### Integration Points
- `opticodds_consumer.py:_on_message()` — Add DB write logic after status mapping
- `mismatch_detector.py:compute_status_match()` — Add 6th parameter `opticodds_status`
- `mismatch_detector.py:compute_is_critical()` — Add `opticodds_status` to live-count sources
- All callers of `compute_status_match` — Update to pass `opticodds_status` (grep all call sites)

</code_context>

<specifics>
## Specific Ideas

- The consumer already processes messages and maps statuses (Phase 12). Phase 13 adds the "write to DB" and "match to event" layers on top.
- Phase 12 verifier noted `_write_heartbeat()` is dead code — if wiring it makes sense during this phase, do it; otherwise leave for a future cleanup.
- OpticOdds message schema field names are MEDIUM confidence (D-10 from Phase 12). The consumer logs raw messages for the first 5 — use those logs to validate field names before hardcoding.

</specifics>

<deferred>
## Deferred Ideas

- **Dashboard OpticOdds column** — DASH-02 mapped to Phase 14. Status data will be in the DB after Phase 13 but won't be visible in the UI until Phase 14.
- **OpticOdds health badge** — DASH-01 mapped to Phase 14. Health keys are already deployed (Phase 12); the dashboard badge ships in Phase 14.

None — discussion stayed within phase scope

</deferred>

---

*Phase: 13-status-processing-and-matching*
*Context gathered: 2026-04-03*
