from fastapi import APIRouter, Depends
from app.api.deps import require_role
from app.core.constants import RoleEnum
from app.clients.prophetx import ProphetXClient
from app.clients.sportsdataio import SportsDataIOClient
import structlog

log = structlog.get_logger()
router = APIRouter(prefix="/probe", tags=["probe"])


@router.get("/clients", dependencies=[Depends(require_role(RoleEnum.admin))])
async def probe_api_clients():
    """
    Phase 1 validation endpoint: test ProphetX and SportsDataIO authentication.
    Calls both APIs and returns response summaries. Full raw responses logged at DEBUG level.
    Admin-only — do not expose to operators or read-only users.
    """
    results = {}

    async with ProphetXClient() as px:
        try:
            raw = await px.get_tournaments_raw()
            results["prophetx"] = {
                "status": "ok",
                "response_type": type(raw).__name__,
                "keys_or_count": list(raw.keys()) if isinstance(raw, dict) else len(raw),
            }
        except Exception as e:
            results["prophetx"] = {"status": "error", "error": str(e)}

    async with SportsDataIOClient() as sdio:
        try:
            coverage = await sdio.probe_subscription_coverage()
            results["sportsdataio"] = {
                "status": "ok",
                "subscription_coverage": coverage,
            }
        except Exception as e:
            results["sportsdataio"] = {"status": "error", "error": str(e)}

    return results
