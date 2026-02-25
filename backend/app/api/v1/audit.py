from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.constants import RoleEnum
from app.db.session import get_async_session
from app.models.audit_log import AuditLog
from app.schemas.audit import AuditLogPage

router = APIRouter(prefix="/audit-log", tags=["audit"])


@router.get(
    "",
    response_model=AuditLogPage,
    dependencies=[Depends(require_role(RoleEnum.operator, RoleEnum.admin))],
)
async def get_audit_log(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_async_session),
):
    """Return paginated audit log entries ordered newest-first.

    Accessible to Operator and Admin roles only.
    """
    offset = (page - 1) * per_page
    total_q = await session.execute(select(func.count()).select_from(AuditLog))
    total = total_q.scalar_one()
    rows_q = await session.execute(
        select(AuditLog)
        .order_by(AuditLog.timestamp.desc())
        .offset(offset)
        .limit(per_page)
    )
    entries = rows_q.scalars().all()
    return AuditLogPage(total=total, page=page, per_page=per_page, entries=entries)
