"""
Seed script: creates admin user and poll interval config from env vars.
Run as: python -m app.seed
"""
import structlog
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app.core.config import settings
from app.core.constants import RoleEnum
from app.core.security import hash_password
from app.db.sync_session import SyncSessionLocal
from app.models.config import SystemConfig
from app.models.user import User

log = structlog.get_logger()

# Default poll interval values (seconds) — seeded from env vars / hardcoded defaults.
# DB becomes sole source of truth after initial seed; env vars are ignored once rows exist.
INTERVAL_DEFAULTS = {
    "poll_interval_prophetx": str(settings.POLL_INTERVAL_PROPHETX),        # 300
    "poll_interval_sports_data": str(settings.POLL_INTERVAL_SPORTS_DATA),  # 30
    "poll_interval_odds_api": str(settings.POLL_INTERVAL_ODDS_API),        # 600
    "poll_interval_espn": str(settings.POLL_INTERVAL_ESPN),                # 600
    "poll_interval_oddsblaze": str(settings.POLL_INTERVAL_ODDSBLAZE),      # 120
    "poll_interval_critical_check": "30",                                   # lowered from 60s (DB query is cheap)
}

# Minimum floor values (seconds) — prevents API abuse. DB-configurable so they
# can be tuned without a code deploy.
INTERVAL_MINIMUMS = {
    "poll_interval_prophetx_min": "60",
    "poll_interval_sports_data_min": "15",
    "poll_interval_odds_api_min": "600",       # hard floor: 500 calls/month free tier
    "poll_interval_espn_min": "60",
    "poll_interval_oddsblaze_min": "30",
    "poll_interval_critical_check_min": "15",
}

# Source enable/disable toggles — "true" or "false". When disabled, the worker
# skips polling, clears its source column, and recomputes status_match so stale
# data doesn't cause false-positive alerts on the dashboard.
SOURCE_ENABLED_DEFAULTS = {
    "source_enabled_odds_api": ("true", "Enable Odds API polling source"),
    "source_enabled_sports_data": ("true", "Enable SportsDataIO polling source"),
    "source_enabled_espn": ("true", "Enable ESPN polling source"),
    "source_enabled_oddsblaze": ("true", "Enable OddsBlaze polling source"),
}


def seed_intervals(session):
    """Insert poll interval and minimum config rows if they don't already exist.

    Seeds 12 rows total: 6 interval values + 6 minimum floors.
    Skips any key that already has a row (preserves operator-configured values).
    """
    all_keys = {
        **{k: (v, "Poll interval (seconds) — seeded from env/defaults") for k, v in INTERVAL_DEFAULTS.items()},
        **{k: (v, "Minimum poll interval floor (seconds) — prevents API abuse") for k, v in INTERVAL_MINIMUMS.items()},
        **SOURCE_ENABLED_DEFAULTS,
    }

    for key, (default_value, description) in all_keys.items():
        existing = session.execute(
            select(SystemConfig).where(SystemConfig.key == key)
        ).scalar_one_or_none()
        if existing is not None:
            log.info("seed_interval_skip", key=key, reason="already exists")
            continue
        session.add(SystemConfig(
            key=key,
            value=default_value,
            description=description,
        ))
        log.info("seed_interval_created", key=key, value=default_value)

    session.commit()
    log.info("seed_intervals_complete", total_keys=len(all_keys))


def seed():
    """Create admin user and seed poll interval config if not already present."""
    try:
        with SyncSessionLocal() as session:
            # --- Admin user seed ---
            existing = session.execute(
                select(User).where(User.email == settings.ADMIN_EMAIL)
            ).scalar_one_or_none()

            if existing:
                log.info("seed_skip", reason="admin user already exists", email=settings.ADMIN_EMAIL)
            else:
                admin = User(
                    email=settings.ADMIN_EMAIL,
                    password_hash=hash_password(settings.ADMIN_PASSWORD),
                    role=RoleEnum.admin,
                    name="Admin",
                    is_active=True,
                )
                session.add(admin)
                session.commit()
                log.info("seed_complete", email=settings.ADMIN_EMAIL, role="admin")

            # --- Poll interval seed ---
            seed_intervals(session)

    except OperationalError as e:
        log.warning("seed_skip", reason="DB not ready yet", error=str(e))
    except Exception as e:
        log.error("seed_failed", error=str(e))
        raise


if __name__ == "__main__":
    seed()
