"""
ProphetX poll worker — runs every 30 seconds via Celery Beat (RedBeat).

Steps:
1. Fetch events and markets from ProphetX API
2. Log observed status values (CRITICAL: enables SDIO_TO_PX_STATUS calibration)
3. Upsert events to DB
4. Upsert markets to DB
5. Detect liquidity breaches per market (logs WARNING; does not alert yet — Plan 02-03)
6. Commit and log summary
"""

import asyncio
import json as _json
from datetime import datetime, timezone

import redis as _sync_redis
import structlog
from sqlalchemy import select

from app.clients.prophetx import ProphetXClient
from app.db.sync_session import SyncSessionLocal
from app.models.event import Event
from app.models.market import Market
from app.monitoring.liquidity_monitor import is_below_threshold
from app.monitoring.mismatch_detector import compute_status_match
from app.workers.celery_app import celery_app
from app.workers.send_alerts import run as send_alerts_task

log = structlog.get_logger()


def _publish_update(update_type: str, entity_id: str) -> None:
    """Publish a state change to the SSE pub/sub channel."""
    from app.core.config import settings
    r = _sync_redis.from_url(settings.REDIS_URL)
    r.publish("prophet:updates", _json.dumps({
        "type": update_type,
        "entity_id": entity_id,
    }))


def _write_heartbeat(worker_name: str) -> None:
    """Write worker heartbeat key — TTL is 3x poll interval so health check survives slight delays."""
    from app.core.config import settings
    r = _sync_redis.from_url(settings.REDIS_URL)
    r.set(f"worker:heartbeat:{worker_name}", "1", ex=settings.POLL_INTERVAL_PROPHETX * 3)


@celery_app.task(name="app.workers.poll_prophetx.run", bind=True, max_retries=3)
def run(self):
    """Fetch ProphetX events + markets, upsert to DB, detect liquidity breaches."""
    try:
        # ------------------------------------------------------------------ #
        # 1. Fetch from ProphetX API (async client, run in sync Celery task)  #
        # ------------------------------------------------------------------ #
        async def _fetch():
            async with ProphetXClient() as px:
                events = await px.get_events_raw()

                # ProphetX requires event_id — fetch markets per event then flatten
                # Response shape: {"data": {"sport_events": [...]}}
                _data = events.get("data", events) if isinstance(events, dict) else events
                if isinstance(_data, dict):
                    _data = _data.get("sport_events", _data.get("events", []))
                events_list = _data if isinstance(_data, list) else []
                event_ids = [
                    str(e.get("event_id") or e.get("id"))
                    for e in events_list
                    if isinstance(e, dict) and (e.get("event_id") or e.get("id"))
                ]

                all_markets: list = []
                for eid in event_ids:
                    try:
                        m = await px.get_markets_raw(event_id=eid)
                        # Response: {"data": {"event_id": ..., "markets": [...]}}
                        m_data = m.get("data", m) if isinstance(m, dict) else m
                        if isinstance(m_data, dict):
                            m_list = m_data.get("markets", [])
                        elif isinstance(m_data, list):
                            m_list = m_data
                        else:
                            m_list = []
                        # Inject event_id into each market (not present in individual market objects)
                        for market in m_list:
                            if isinstance(market, dict) and not market.get("event_id"):
                                market["event_id"] = eid
                        all_markets.extend(m_list)
                    except Exception as market_exc:
                        log.warning("prophetx_markets_fetch_failed_for_event", event_id=eid, error=str(market_exc))

                return events, all_markets

        raw_events, raw_markets = asyncio.run(_fetch())

    except Exception as exc:
        log.error(
            "poll_prophetx_fetch_failed",
            error=str(exc),
            retry=self.request.retries,
        )
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)

    # ------------------------------------------------------------------ #
    # 2. CRITICAL: Log all unique status values observed in this response  #
    # This output is required to confirm/correct SDIO_TO_PX_STATUS values. #
    # See RESEARCH.md Open Questions #1 and #2.                            #
    # ------------------------------------------------------------------ #
    if isinstance(raw_events, list):
        events_list = raw_events
    elif isinstance(raw_events, dict):
        # ProphetX response shape: {"data": {"sport_events": [...]}}
        _lvl1 = raw_events.get("data", raw_events.get("events", raw_events))
        if isinstance(_lvl1, dict):
            _lvl1 = _lvl1.get("sport_events", _lvl1.get("events", [_lvl1]))
        events_list = _lvl1 if isinstance(_lvl1, list) else [_lvl1]
    else:
        events_list = []

    statuses = {
        e.get("status") or e.get("event_status") or "UNKNOWN_FIELD"
        for e in events_list
        if isinstance(e, dict)
    }
    log.info("prophetx_status_values_observed", statuses=sorted(statuses))

    if isinstance(raw_markets, list):
        markets_list = raw_markets
    elif isinstance(raw_markets, dict):
        markets_list = raw_markets.get("data", raw_markets.get("markets", [raw_markets]))
        if isinstance(markets_list, dict):
            markets_list = [markets_list]
    else:
        markets_list = []

    if markets_list:
        first_market = markets_list[0] if isinstance(markets_list[0], dict) else {}
        log.info("prophetx_market_fields", fields=list(first_market.keys()))

    # ------------------------------------------------------------------ #
    # 3–5. Upsert events, upsert markets, detect liquidity breaches        #
    # ------------------------------------------------------------------ #
    events_upserted = 0
    markets_upserted = 0
    liquidity_alerts = 0
    events_marked_ended = 0
    now = datetime.now(timezone.utc)

    # Track which ProphetX event IDs appear in this poll response.
    # Events missing from the response that were previously live/upcoming are
    # assumed ended — ProphetX only returns active events via get_sport_events.
    polled_px_ids: set[str] = set()

    with SyncSessionLocal() as session:
        # -- Upsert events --
        for raw_event in events_list:
            if not isinstance(raw_event, dict):
                continue

            prophetx_event_id = raw_event.get("id") or raw_event.get("event_id")
            if not prophetx_event_id:
                log.warning(
                    "prophetx_event_missing_id",
                    raw_keys=list(raw_event.keys()),
                )
                continue

            prophetx_event_id = str(prophetx_event_id)

            # Detect status field name (may vary between API responses)
            status_value = (
                raw_event.get("status")
                or raw_event.get("event_status")
                or raw_event.get("state")
            )

            # Extract home/away from competitors array (ProphetX structure)
            competitors = raw_event.get("competitors") or []
            home_team = next(
                (c.get("name") or c.get("display_name") for c in competitors if c.get("side") == "home"),
                raw_event.get("home_team") or raw_event.get("home"),
            )
            away_team = next(
                (c.get("name") or c.get("display_name") for c in competitors if c.get("side") == "away"),
                raw_event.get("away_team") or raw_event.get("away"),
            )
            # Fallback: parse "Away at Home" from event name when competitors array is empty
            if not home_team and not away_team:
                event_name = raw_event.get("name") or raw_event.get("display_name") or ""
                if " at " in event_name:
                    parts = event_name.split(" at ", 1)
                    away_team = parts[0].strip()
                    home_team = parts[1].strip()

            # Parse scheduled start — accept ISO string or unix timestamp
            scheduled_raw = (
                raw_event.get("scheduled")
                or raw_event.get("scheduled_start")
                or raw_event.get("start_time")
                or raw_event.get("starts_at")
            )
            scheduled_start = None
            if scheduled_raw is not None:
                try:
                    if isinstance(scheduled_raw, (int, float)):
                        scheduled_start = datetime.fromtimestamp(scheduled_raw, tz=timezone.utc)
                    else:
                        scheduled_start = datetime.fromisoformat(str(scheduled_raw))
                        if scheduled_start.tzinfo is None:
                            scheduled_start = scheduled_start.replace(tzinfo=timezone.utc)
                except Exception as e:
                    log.warning(
                        "prophetx_event_invalid_start_time",
                        event_id=prophetx_event_id,
                        value=scheduled_raw,
                        error=str(e),
                    )

            # SELECT then INSERT/UPDATE (works with any DB setup)
            existing = session.execute(
                select(Event).where(Event.prophetx_event_id == prophetx_event_id)
            ).scalar_one_or_none()

            if existing is None:
                event = Event(
                    prophetx_event_id=prophetx_event_id,
                    sport=str(raw_event.get("sport") or raw_event.get("sport_name") or raw_event.get("league_name") or "unknown"),
                    name=str(raw_event.get("name") or raw_event.get("title") or prophetx_event_id),
                    home_team=home_team,
                    away_team=away_team,
                    scheduled_start=scheduled_start,
                    prophetx_status=status_value,
                    last_prophetx_poll=now,
                )
                session.add(event)
            else:
                existing.sport = str(
                    raw_event.get("sport") or raw_event.get("sport_name") or raw_event.get("league_name") or existing.sport
                )
                existing.name = str(
                    raw_event.get("name") or raw_event.get("title") or existing.name
                )
                existing.home_team = home_team or existing.home_team
                existing.away_team = away_team or existing.away_team
                if scheduled_start is not None:
                    existing.scheduled_start = scheduled_start
                existing.prophetx_status = status_value
                existing.last_prophetx_poll = now
                existing.status_match = compute_status_match(
                    status_value,
                    existing.odds_api_status,
                    existing.sports_api_status,
                    existing.sdio_status,
                    existing.espn_status,
                )

            polled_px_ids.add(prophetx_event_id)
            events_upserted += 1
            # Publish SSE update after event upsert
            _publish_update("event_updated", str(prophetx_event_id))

        # Flush events before upserting markets (FK lookup needs event rows)
        session.flush()

        # -- Upsert markets --
        for raw_market in markets_list:
            if not isinstance(raw_market, dict):
                continue

            prophetx_market_id = raw_market.get("id") or raw_market.get("market_id")
            if not prophetx_market_id:
                log.warning(
                    "prophetx_market_missing_id",
                    raw_keys=list(raw_market.keys()),
                )
                continue

            prophetx_market_id = str(prophetx_market_id)

            # Resolve parent event FK
            event_prophetx_id = (
                raw_market.get("event_id")
                or raw_market.get("sport_event_id")
            )
            event_db_id = None
            if event_prophetx_id:
                parent = session.execute(
                    select(Event).where(
                        Event.prophetx_event_id == str(event_prophetx_id)
                    )
                ).scalar_one_or_none()
                if parent:
                    event_db_id = parent.id

            if event_db_id is None:
                log.warning(
                    "prophetx_market_no_parent_event",
                    market_id=prophetx_market_id,
                    event_prophetx_id=event_prophetx_id,
                )
                continue

            # Identify liquidity field — log uncertainty if not found
            liquidity_raw = (
                raw_market.get("liquidity")
                or raw_market.get("current_liquidity")
                or raw_market.get("available_liquidity")
                or raw_market.get("volume")
            )
            if liquidity_raw is None:
                log.warning(
                    "prophetx_market_liquidity_field_not_found",
                    market_id=prophetx_market_id,
                    available_fields=list(raw_market.keys()),
                )

            from decimal import Decimal

            try:
                liquidity_value = Decimal(str(liquidity_raw)) if liquidity_raw is not None else Decimal("0")
            except Exception:
                liquidity_value = Decimal("0")

            market_name = str(
                raw_market.get("name") or raw_market.get("title") or prophetx_market_id
            )
            market_status = str(raw_market.get("status") or "active")

            existing_market = session.execute(
                select(Market).where(Market.prophetx_market_id == prophetx_market_id)
            ).scalar_one_or_none()

            if existing_market is None:
                market = Market(
                    prophetx_market_id=prophetx_market_id,
                    event_id=event_db_id,
                    name=market_name,
                    current_liquidity=liquidity_value,
                    status=market_status,
                    last_polled=now,
                )
                session.add(market)
                session.flush()
                market_obj = market
            else:
                existing_market.name = market_name
                existing_market.current_liquidity = liquidity_value
                existing_market.status = market_status
                existing_market.last_polled = now
                market_obj = existing_market

            markets_upserted += 1
            # Publish SSE update after market upsert
            _publish_update("market_updated", str(market_obj.id))

            # 5. Liquidity breach check — enqueue alert (LIQ-02)
            if is_below_threshold(market_obj, session):
                log.warning(
                    "liquidity_breach_detected",
                    market_id=str(market_obj.id),
                    prophetx_market_id=prophetx_market_id,
                    current_liquidity=str(market_obj.current_liquidity),
                    event_id=str(event_db_id),
                )
                send_alerts_task.delay(
                    alert_type="liquidity_alert",
                    entity_type="market",
                    entity_id=str(market_obj.id),
                    message=f"Market {market_obj.name} liquidity {market_obj.current_liquidity} below threshold",
                )
                liquidity_alerts += 1

        # -- Mark stale events as ended --
        # ProphetX only returns active (live/upcoming) events. If an event was
        # previously live or upcoming, is no longer in the response, and its
        # scheduled_start is in the past, it has ended on ProphetX but we never
        # received the update because it silently dropped off the response.
        from datetime import timedelta
        from sqlalchemy import and_

        ACTIVE_STATUSES = {"live", "upcoming", "not_started", "pre-event"}
        stale_cutoff = now - timedelta(hours=3)  # must be > 3h past scheduled_start

        stale_events = session.execute(
            select(Event).where(
                and_(
                    Event.scheduled_start <= stale_cutoff,
                )
            )
        ).scalars().all()

        for event in stale_events:
            if (
                str(event.prophetx_event_id) not in polled_px_ids
                and (event.prophetx_status or "").lower() in ACTIVE_STATUSES
            ):
                log.info(
                    "prophetx_event_marked_ended",
                    prophetx_event_id=event.prophetx_event_id,
                    previous_status=event.prophetx_status,
                    scheduled_start=str(event.scheduled_start),
                )
                event.prophetx_status = "ended"
                event.last_prophetx_poll = now
                event.status_match = compute_status_match(
                    "ended",
                    event.odds_api_status,
                    event.sports_api_status,
                    event.sdio_status,
                    event.espn_status,
                )
                events_marked_ended += 1
                _publish_update("event_updated", str(event.prophetx_event_id))

        # Recompute status_match for all events from current source columns.
        # Source workers only update status_match on events they match — events
        # that fall out of a source's date window retain stale values forever
        # without this pass.
        all_events = session.execute(select(Event)).scalars().all()
        for event in all_events:
            computed = compute_status_match(
                event.prophetx_status,
                event.odds_api_status,
                event.sports_api_status,
                event.sdio_status,
                event.espn_status,
            )
            if event.status_match != computed:
                event.status_match = computed

        session.commit()

    # Write heartbeat key — read by /health/workers to confirm worker is alive
    _write_heartbeat("poll_prophetx")

    log.info(
        "poll_prophetx_complete",
        events=events_upserted,
        markets=markets_upserted,
        liquidity_alerts=liquidity_alerts,
        events_marked_ended=events_marked_ended,
    )
