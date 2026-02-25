"""
Liquidity Monitor — threshold resolution and breach detection.

No network dependencies. Uses sync DB session passed in by caller.
Fully testable in isolation via mocked session.

Key functions:
- get_effective_threshold(): market threshold -> global default -> 0 (safe)
- is_below_threshold(): True when market liquidity is below effective threshold
"""

from decimal import Decimal

import structlog
from sqlalchemy.orm import Session

from app.models.config import SystemConfig

log = structlog.get_logger()


def get_effective_threshold(market, session: Session) -> Decimal:
    """Return the liquidity threshold for a market.

    Resolution order:
    1. market.min_liquidity_threshold if set (per-market override)
    2. SystemConfig key "default_min_liquidity" (global default)
    3. Decimal("0") if no threshold configured (logs a warning)

    Args:
        market: Market ORM instance with min_liquidity_threshold attribute.
        session: Active SQLAlchemy sync session.

    Returns:
        Effective threshold as Decimal.
    """
    if market.min_liquidity_threshold is not None:
        return Decimal(market.min_liquidity_threshold)

    # Fall back to global default from system_config table
    row = (
        session.query(SystemConfig)
        .filter(SystemConfig.key == "default_min_liquidity")
        .first()
    )

    if row is None:
        log.warning(
            "no_default_liquidity_threshold_configured",
            market_id=str(getattr(market, "id", "unknown")),
            action="returning_zero_threshold",
        )
        return Decimal("0")

    return Decimal(row.value)


def is_below_threshold(market, session: Session) -> bool:
    """Return True when market's current liquidity is below its effective threshold.

    Safe defaults:
    - If threshold is 0 (not configured), returns False — no alert without a threshold.
    - Never raises on missing config.

    Args:
        market: Market ORM instance with current_liquidity and min_liquidity_threshold.
        session: Active SQLAlchemy sync session.

    Returns:
        True if market needs a liquidity alert, False otherwise.
    """
    threshold = get_effective_threshold(market, session)
    if threshold == Decimal("0"):
        return False
    return Decimal(market.current_liquidity) < threshold
