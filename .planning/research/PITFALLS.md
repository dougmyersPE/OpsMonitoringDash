# Pitfalls Research

**Domain:** Adding WebSocket-primary status authority to an existing polling-based event monitoring system (ProphetX Market Monitor v1.2)
**Researched:** 2026-03-31
**Confidence:** HIGH for pysher/Pusher behavior (confirmed from official docs + source); HIGH for existing codebase-specific pitfalls (direct inspection); MEDIUM for race condition patterns (general literature, confirmed against codebase structure); HIGH for token-expiry gap (confirmed Pusher docs + current ws_prophetx.py design)

---

## Critical Pitfalls

### Pitfall 1: Events Lost During the Token-Expiry Reconnect Window

**What goes wrong:**
The current `ws_prophetx.py` design proactively disconnects and reconnects every ~20 minutes when the ProphetX access token is about to expire. Pusher does not buffer or replay events during this disconnect window. Any `sport_event` change messages published by ProphetX while the WS consumer is reconnecting are silently lost — they are never delivered, and the system has no awareness of the gap.

In a quiet period this is harmless. In a busy window (multiple games going live or ending simultaneously), a 10–30 second reconnect gap could miss `live` or `ended` transitions for several events. The polling fallback (`poll_prophetx` every 30 seconds) is designed to catch this, but only if it runs within the window and only if it catches the current state of all affected events.

**Why it happens:**
Pusher's event delivery model is fire-and-forget with no message persistence. The [official docs](https://docs.bird.com/pusher/channels/channels/events/how-can-i-get-missed-messages-after-reconnecting-to-channels) state explicitly: "when that happens new messages won't be able to be delivered to that client." The gap is inherent to the push architecture, not a Pysher bug.

The existing `run()` loop has clean intent — disconnect before expiry, reconnect with fresh token — but does not trigger an immediate reconciliation poll to close the gap. The 5-minute polling interval means a missed transition can persist for up to 5 minutes before polling catches it.

**How to avoid:**
After every successful reconnect (when `_connect_and_run()` returns cleanly due to token expiry), publish a Redis signal or trigger a one-shot `poll_prophetx` task immediately. This forces the reconciliation worker to run at the reconnect moment rather than waiting for its next scheduled window.

Do not rely solely on the scheduled 30-second `poll_prophetx` interval to cover this gap; a 30-second poll window during a busy transition period is adequate, but a 5-minute poll interval is not.

Alternatively, overlap token refresh: before disconnecting, acquire a new token and reconnect, then tear down the old connection — no gap at all. This is architecturally cleaner but requires holding two pysher clients briefly.

**Warning signs:**
- Events in the DB still show `not_started` after their game has gone live, then suddenly jump to `live` 1–5 minutes later
- `ws_prophetx_token_expiring_reconnect` log entries correlate temporally with status lag reports
- Dashboard shows events that were `live` on other sources while ProphetX still showed `not_started`

**Phase to address:** Phase 1 (WS diagnostics and end-to-end verification) — ensure the reconnect procedure triggers a reconciliation poll. This must be addressed before elevating WS authority, because the gap proves the fallback reliance is still required.

---

### Pitfall 2: Pysher Maintenance Mode — Silent Disconnect Detection Unreliable

**What goes wrong:**
Pysher is explicitly in maintenance mode (no active maintainer as of 2026). It relies on `websocket-client` for the underlying connection. The internal reconnect_interval=5 parameter tells pysher to attempt reconnection after a drop, but pysher has no application-level heartbeat of its own — it relies on the network stack to detect the dropped connection.

In production, TCP connections can appear "alive" to the application layer while being silently broken at the network level (NAT timeout, proxy reset, server-side idle timeout). The Pusher protocol supports `pusher:ping` / `pusher:pong` keepalives, but pysher does not implement the application-level ping mechanism. This means the worker can sit in a state where it believes it is connected, is writing heartbeats every 10 seconds, and the health endpoint shows "green" — but no events are being received.

**Why it happens:**
The current `_connect_and_run()` loop calls `time.sleep(10); _write_heartbeat()` in a tight loop. It writes the heartbeat regardless of whether any messages have been received. The health check reads the heartbeat TTL key — it cannot distinguish "connected and receiving messages" from "connected but silently dead."

The heartbeat key currently has a 90-second TTL. If the connection silently dies but the sleep loop continues writing the key, the health endpoint will report "healthy" indefinitely while no events are processed.

**How to avoid:**
Supplement the connection-alive heartbeat with a message-received counter or last-message-at timestamp in Redis. The health endpoint should report "degraded" if no `sport_event` message has been received in X minutes (where X is calibrated to expected message frequency). During active seasons, sport_event messages should arrive frequently; 5+ minutes with zero messages is suspicious.

Also: set a maximum silence threshold on the WS loop — if zero `sport_event` messages have arrived in, say, 10 minutes, force a reconnect even if the connection appears established.

**Warning signs:**
- `/health/workers` shows `ws_prophetx: true` but the event dashboard shows stale statuses
- `ws_prophetx_event_updated` log entries have stopped appearing, but `ws_prophetx_heartbeat_written` continues
- Redis key `worker:heartbeat:ws_prophetx` exists with full TTL but no recent DB writes from the WS consumer

**Phase to address:** Phase 2 (WS connection health surfaced on dashboard) — the dashboard health widget must show more than a binary up/down. It should reflect message activity, not just heartbeat presence.

---

### Pitfall 3: WS and Polling Write the Same Row Concurrently — Status Regression via Race

**What goes wrong:**
When WS status authority is elevated, both `ws_prophetx.py` (running continuously in its own Docker service) and `poll_prophetx` (running every 30 seconds via Celery) write to the same `events` table row. They both read-then-write `prophetx_status` without coordinated locking. A race is possible:

1. WS receives `sport_event` op=u with status=`live` → reads row, writes `live`, commits.
2. Meanwhile, `poll_prophetx` fetches the REST API. The REST response was cached/assembled before the WS message arrived — it still shows `not_started`.
3. `poll_prophetx` reads the row (now `live`), overwrites `prophetx_status = not_started`, commits.
4. The lifecycle guard in `update_event_status.py` is in the action worker, not in the poll worker's upsert path. The poll worker writes backward status directly.

Result: the event regresses from `live` back to `not_started` until the next WS message or poll cycle catches it. If the lifecycle guard isn't applied in `poll_prophetx`'s upsert loop, the polling fallback can silently undo WS-delivered status advances.

**Why it happens:**
The lifecycle guard (`_LIFECYCLE_ORDER` check in `update_event_status.py`) exists in the action worker, not in the poll worker's direct DB upsert path. `poll_prophetx` unconditionally overwrites `prophetx_status = status_value` (lines 219 and 147 of `poll_prophetx.py`) without checking whether the new value would be a regression from what's already in the DB. This was correct pre-v1.2 when polling was the sole authority, but becomes a race hazard once WS can advance status ahead of polling.

**How to avoid:**
Apply the lifecycle guard in both write paths. In `poll_prophetx`'s upsert loop, before overwriting `existing.prophetx_status`, check: if the existing status is already more advanced than `status_value`, do not overwrite. This mirrors the guard logic already in `update_event_status.py`.

```python
# In poll_prophetx.py existing-event update block:
_LIFECYCLE_ORDER = {"not_started": 0, "upcoming": 0, "live": 1, "ended": 2, "settled": 2}
current_rank = _LIFECYCLE_ORDER.get((existing.prophetx_status or "").lower(), -1)
incoming_rank = _LIFECYCLE_ORDER.get((status_value or "").lower(), -1)
if incoming_rank < current_rank:
    # Poll response is behind WS-delivered status — do not regress
    pass
else:
    existing.prophetx_status = status_value
```

Apply the same guard in `ws_prophetx.py`'s `_upsert_event()` for symmetry.

**Warning signs:**
- Events flicker between `not_started` and `live` in the dashboard during game-time windows
- Audit log shows rapid alternating status updates: `live → not_started → live`
- `ws_prophetx_event_updated` log entry immediately followed by `poll_prophetx_complete` with regression visible in DB

**Phase to address:** Phase 3 (ProphetX REST poller demoted to reconciliation fallback) — the lifecycle guard must be present in the poll worker's upsert path before demotion. Without it, demotion introduces the regression race.

---

### Pitfall 4: WS `_upsert_event()` Creates New Events Without status_match Computation

**What goes wrong:**
In `ws_prophetx.py`, the `_upsert_event()` function creates new `Event` rows (the `existing is None` branch, lines 177–198) without setting `status_match`. The field is left NULL on new WS-created events. The mismatch detector and dashboard query depend on `status_match` being populated; NULL is treated as "unknown" or causes display anomalies depending on the query.

Contrast with the `existing` branch (lines 212–219): it does compute and store `status_match`. But newly created events from WS payloads skip it entirely.

**Why it happens:**
Copy-paste from `poll_prophetx.py` where the same asymmetry originally existed. When `status_match` was added as a computed column, it was added to the update-existing path but not the insert-new path.

**How to avoid:**
In `_upsert_event()`'s `existing is None` branch, compute `status_match` at creation time using the new event's `prophetx_status` and `None` for all source statuses (since the event is brand new and no external sources have data yet). This correctly initializes `status_match = True` (all sources absent, no conflict).

```python
event = Event(
    ...
    prophetx_status=status_value,
    status_match=compute_status_match(status_value, None, None, None, None, None),
    last_prophetx_poll=now,
)
```

**Warning signs:**
- New events created by WS consumer show NULL in `status_match` column
- Events created via WS don't appear in mismatch alerts even when sources disagree
- Dashboard "unknown" status badges on events that were first seen via WS

**Phase to address:** Phase 1 (WS diagnostics and end-to-end verification) — this is a pre-existing bug in the current `ws_prophetx.py` that should be fixed as part of confirming end-to-end WS operation.

---

### Pitfall 5: Treating WS Message Receipt as Proof of Channel Subscription Success

**What goes wrong:**
The current `_connect_and_run()` code calls `pusher_client.subscribe(BROADCAST_CHANNEL)` and then immediately patches `_handle_event` on the returned channel object. There is no wait for `pusher:subscription_succeeded` before declaring the consumer operational. If the subscription request is rejected (e.g., the auth endpoint returns an error, or the ProphetX-side auth is temporarily unavailable), pysher may hold the channel object in a pending-subscription state without raising an exception — the consumer appears to be running but events are never delivered.

**Why it happens:**
Pusher private/presence channel subscriptions require a server-side auth step. The auth endpoint (`/partner/mm/pusher`) must return a signed auth token for the subscription to be approved. If auth fails silently (e.g., a 4xx that pysher doesn't surface as an exception), the channel subscription never completes but the process continues writing heartbeats.

The `connection_ready` event fires on `pusher:connection_established` — which only confirms the WebSocket connection itself, not channel subscription success.

**How to avoid:**
Bind a handler to the `pusher:subscription_succeeded` event on the channel, and track whether subscription has been confirmed. Log the confirmation explicitly. Optionally: if `subscription_succeeded` has not fired within 30 seconds of `subscribe()`, disconnect and reconnect (treat as a failed subscription).

```python
subscription_confirmed = threading.Event()

def _on_subscription_succeeded(data):
    log.info("ws_prophetx_subscription_confirmed", channel=BROADCAST_CHANNEL)
    subscription_confirmed.set()

channel.bind("pusher:subscription_succeeded", _on_subscription_succeeded)

if not subscription_confirmed.wait(timeout=30):
    log.error("ws_prophetx_subscription_timeout", channel=BROADCAST_CHANNEL)
    pusher_client.disconnect()
    raise RuntimeError("Pusher subscription timed out after 30s")
```

**Warning signs:**
- `ws_prophetx_connected` log entry present but no subsequent event activity
- Auth endpoint returns 4xx responses visible in ProphetX API logs
- Subscription never emits `pusher:subscription_succeeded` in pysher DEBUG logs

**Phase to address:** Phase 1 (WS diagnostics) — adding subscription confirmation logging is a low-cost diagnostic improvement that immediately surfaces this failure mode.

---

### Pitfall 6: Mismatch Direction Inversion After Authority Elevation

**What goes wrong:**
Currently, `compute_status_match()` in `mismatch_detector.py` checks whether the external sources agree with `prophetx_status`. ProphetX is the value being validated against external ground truth. After WS elevation, ProphetX IS the ground truth for current status — but the mismatch logic is not semantically changed by this architectural shift.

The subtle inversion risk: with WS as authority, a mismatch now means "an external source hasn't caught up to what ProphetX already knows" rather than "ProphetX is behind the real world." Applying the same alert thresholds and auto-correction logic unchanged could trigger false-positive alerts when ProphetX goes `live` via WS seconds before SDIO updates, causing the system to "correct" a correct status.

The lifecycle guard prevents regression, but the mismatch detector could still fire alerts and queue status-update tasks for events where ProphetX is already correct and external sources just haven't caught up.

**Why it happens:**
The v1.0/v1.1 mental model was "external sources are authoritative, ProphetX may be behind." The v1.2 model is "WS-delivered ProphetX status is authoritative, external sources are validators." The code structure doesn't automatically flip this interpretation — mismatch detection logic reads the same either way.

**How to avoid:**
In v1.2, add a `ws_last_updated` timestamp column (or use `last_prophetx_poll` set by the WS consumer). When `compute_is_critical()` or any alert logic fires, first check: was this event's ProphetX status set within the last N seconds by the WS consumer? If yes, the external source lag is expected and the mismatch is not actionable. The auto-correction path should not queue a status-update task when ProphetX's WS-delivered status is more advanced than external sources.

This is a semantics change, not a code rewrite — but it must be explicitly addressed.

**Warning signs:**
- Burst of false-positive mismatch alerts exactly when multiple games go live (WS delivers `live` before external sources update)
- `update_event_status` tasks queued for events where ProphetX was already correctly `live`
- Alert log shows "ProphetX behind" for events ProphetX set as `live` 10 seconds ago

**Phase to address:** Phase 3 (ProphetX REST poller demotion + reconciliation model) — when the role of polling changes, the mismatch detector's alerting thresholds and direction must be re-validated.

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Skip lifecycle guard in poll worker upsert | Simpler code, no ordering logic needed | WS-delivered `live` status gets regressed to `not_started` by next poll | Never once WS is primary authority |
| Single heartbeat key for both "connected" and "receiving messages" | Simple health check | Health endpoint shows green during a silently dead connection | Never for production; split into separate keys |
| No gap-close poll after WS reconnect | No extra implementation work | Transitions missed during reconnect window persist until next scheduled poll | Never — gap window must be closed actively |
| Rely only on scheduled `poll_prophetx` as fallback | No code change required | 30s poll interval means a missed WS message causes up to 30s of stale status | Acceptable only if poll interval is ≤ 60s and is explicitly documented as the fallback SLA |
| Skip `status_match` init on WS-created events | Slightly less code | NULL `status_match` causes query anomalies and missed alerts | Never — easy to fix, significant cost to leave |

---

## Integration Gotchas

Common mistakes when connecting to external services.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Pusher private channel | Checking `pusher:connection_established` as proof of subscription readiness | Wait for `pusher:subscription_succeeded` on the channel object before considering events deliverable |
| Pusher + token auth | Assuming a clean disconnect-reconnect has zero message loss | Accept that Pusher has no message persistence; trigger a reconciliation poll immediately after reconnect |
| pysher + ProphetX broadcast channel | Binding named events via `channel.bind("sport_event", ...)` | Broadcast events arrive as `tournament_{id}` — not as `sport_event`. Must patch `_handle_event` on the channel object to catch all events (current implementation already does this correctly) |
| pysher reconnect_interval | Setting a short reconnect_interval expecting fast recovery | pysher's reconnect is internal to websocket-client; the actual reconnect behavior depends on network stack detection of the drop. Silent drops bypass reconnect entirely. |
| ProphetX auth endpoint `/mm/pusher` | Assuming auth always succeeds when the WS connection is established | Auth can fail for reasons independent of WS connectivity (token expired mid-session, ProphetX side 5xx). Bind `pusher:subscription_error` to detect and handle this separately from connection failure. |

---

## Performance Traps

Patterns that work at small scale but fail as usage grows.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Creating a new Redis connection on every heartbeat write | Single event: imperceptible. Burst reconnects: connection pool exhaustion | Reuse Redis connection within a single `_connect_and_run()` invocation; the current pattern creates `_sync_redis.from_url()` per call — acceptable at current 10s intervals, but should not be tightened further | At sub-second heartbeat intervals or during reconnect storms |
| Full `all_events` table scan in `poll_prophetx` to recompute status_match | Fine at 50 events, slow at 5000 | Add index on `prophetx_status`; long-term, remove the full-table pass and compute at upsert time | At ~1000+ events in DB |
| `compute_status_match()` called on every poll cycle for every event | Cheap pure function, but called N×5-source times per cycle | Keep as-is at current scale; do not add network calls inside this function | Not a concern at current 50–500 events |

---

## Security Mistakes

Domain-specific security issues beyond general web security.

| Mistake | Risk | Prevention |
|---------|------|------------|
| Logging the raw WS payload at INFO level when debugging | ProphetX market data (event IDs, competitor names, odds) in log files visible to anyone with Docker log access | Log at DEBUG only; log structural shape (keys, change_type) not payload contents in production |
| Assuming WS-delivered `op=d` (delete) is sufficient authority to mark an event as `ended` | ProphetX could issue a spurious delete for a live event due to a data issue | The current guard `if existing.prophetx_status not in ("ended", "cancelled")` is correct — apply same caution to `ended` forced by delete: require event to be past scheduled_start before accepting WS-delete as `ended` |
| Storing ProphetX access token in a module-level mutable object (`_TokenState`) | Token visible in process memory dump; module reload (rare) clears it, causing mid-cycle auth failure | Acceptable for an internal ops tool on a private VPS; would need secrets management for multi-tenant or public deployment |

---

## UX Pitfalls

Common user experience mistakes in this domain.

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Binary "WS connected: yes/no" health indicator | Operators cannot distinguish "WS connected, receiving events" from "WS connected, silently dead" | Show last-message-received timestamp alongside connection status |
| No visual distinction between WS-sourced and poll-sourced status updates | Operators cannot tell if the status they see is milliseconds fresh (WS) or up to 30 seconds old (poll) | Add a `status_source` field to the event row (`"ws"` or `"poll"`); surface it as a subtle badge on the dashboard |
| Dashboard shows ProphetX status as mismatch immediately after WS delivers `live` | Operators see a false alert, lose trust in the system | Add a brief grace period (30s) before raising a mismatch alert when ProphetX's status is ahead of external sources |

---

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces.

- [ ] **WS consumer is "running":** Verify subscription_succeeded fires, not just connection_established — check Docker logs for `ws_prophetx_subscription_confirmed`
- [ ] **WS delivers sport_event messages:** Confirm `ws_prophetx_event_updated` log entries appear during live game windows, not just `ws_prophetx_non_event_update` (market/market_line only)
- [ ] **Lifecycle guard in poll worker:** Verify `poll_prophetx.py` does not overwrite a WS-delivered `live` status with a polled `not_started` — requires explicit regression guard in the upsert path
- [ ] **Gap closure after reconnect:** Verify a reconciliation poll fires within 60 seconds of every `ws_prophetx_token_expiring_reconnect` log entry
- [ ] **Health dashboard reflects message activity:** Verify the health endpoint or dashboard shows last-message-at, not just heartbeat TTL presence
- [ ] **`status_match` initialized on WS-created events:** Query `SELECT prophetx_event_id, status_match FROM events WHERE status_match IS NULL` — should be empty
- [ ] **No false-positive mismatch alerts on WS-advance:** During a game start window, verify no spurious alerts fire for events where ProphetX went `live` via WS before external sources updated

---

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Events regressed by poll worker overwriting WS status | LOW | Run `poll_prophetx` manually or wait for next WS message; add lifecycle guard to prevent recurrence |
| Silent WS dead connection (health shows green, no events) | LOW | Restart `ws-consumer` Docker service; root-cause via last-message-at timestamp |
| Large gap of missed events from extended WS downtime | MEDIUM | Trigger a manual `poll_prophetx` run immediately; check all active events' statuses match ProphetX REST API |
| Spurious mismatch alerts during WS authority elevation | LOW | Add `status_source` and grace-period logic; manually clear queued `update_event_status` tasks if any incorrect corrections were applied |
| `status_match` NULL on batch of WS-created events | LOW | One-time backfill: `UPDATE events SET status_match = compute_status_match(...)` for all NULL rows; fix insertion code |

---

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Events lost during token-expiry reconnect window | Phase 1: WS diagnostics | Log entries show gap-close poll fires within 60s of every reconnect |
| Pysher silent disconnect — health shows green but no events | Phase 2: Dashboard health widget | Health dashboard shows last-message-at timestamp, not just heartbeat TTL |
| Poll worker regresses WS-delivered status | Phase 3: Poll demotion | No `not_started` overwrites of `live` events visible in audit log during game-time window |
| `_upsert_event()` skips `status_match` on new events | Phase 1: WS diagnostics | `SELECT COUNT(*) FROM events WHERE status_match IS NULL` = 0 after first WS-created event |
| Subscription success assumed from connection success | Phase 1: WS diagnostics | `ws_prophetx_subscription_confirmed` log entries present on every startup |
| Mismatch alert direction inversion after elevation | Phase 3: Poll demotion | Zero false-positive mismatch alerts for events where ProphetX was WS-advanced ahead of external sources |

---

## Sources

- Direct codebase inspection: `backend/app/workers/ws_prophetx.py` — token expiry reconnect loop, heartbeat write pattern, `_upsert_event()` missing `status_match` on insert, no subscription_succeeded guard
- Direct codebase inspection: `backend/app/workers/poll_prophetx.py` — unconditional `prophetx_status` overwrite with no lifecycle guard in upsert path
- Direct codebase inspection: `backend/app/workers/update_event_status.py` — lifecycle guard exists in action worker but not in poll worker upsert
- Direct codebase inspection: `backend/app/monitoring/mismatch_detector.py` — `compute_status_match()` validates ProphetX against external sources; direction inversion after elevation
- Pusher Channels documentation: [Connection states and reconnection](https://pusher.com/docs/channels/using_channels/connection/) — confirmed connected state does not guarantee channel subscription success
- Pusher missed-events documentation: [How Can I Get Missed Messages After Reconnecting](https://docs.bird.com/pusher/channels/channels/events/how-can-i-get-missed-messages-after-reconnecting-to-channels) — confirmed Pusher has no message persistence; clients must implement their own gap recovery
- Pysher GitHub: [deepbrook/Pysher](https://github.com/deepbrook/Pysher) — confirmed maintenance mode; no active maintainer; reconnect behavior relies on `websocket-client` network detection
- Pusher protocol docs: [WebSocket Protocol](https://pusher.com/docs/channels/library_auth_reference/pusher-websockets-protocol/) — confirmed ping/pong keepalive behavior and error codes 4201/4202
- WebSocket reconnection guide: [WebSocket.org Reconnection](https://websocket.org/guides/reconnection/) — confirmed token expiry + reconnect window as production gap source

---
*Pitfalls research for: WebSocket-primary status authority addition to polling-based monitoring (ProphetX Market Monitor v1.2)*
*Researched: 2026-03-31*
