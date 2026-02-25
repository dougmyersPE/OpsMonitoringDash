from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.constants import RoleEnum
from app.db.session import get_async_session
from app.models.config import SystemConfig
from app.schemas.config import ConfigItem, ConfigUpdateRequest

router = APIRouter(prefix="/config", tags=["config"])


@router.get("", response_model=List[ConfigItem], dependencies=[Depends(require_role(RoleEnum.admin))])
async def get_config(session: AsyncSession = Depends(get_async_session)):
    result = await session.execute(select(SystemConfig))
    items = result.scalars().all()
    return [ConfigItem(key=i.key, value=i.value, description=i.description) for i in items]


@router.patch("/{key}", response_model=ConfigItem, dependencies=[Depends(require_role(RoleEnum.admin))])
async def update_config(
    key: str,
    body: ConfigUpdateRequest,
    session: AsyncSession = Depends(get_async_session),
):
    result = await session.execute(select(SystemConfig).where(SystemConfig.key == key))
    item = result.scalar_one_or_none()
    if item is None:
        # Upsert: create if not exists
        item = SystemConfig(key=key, value=body.value, description=body.description)
        session.add(item)
    else:
        item.value = body.value
        if body.description is not None:
            item.description = body.description
    await session.commit()
    await session.refresh(item)
    return ConfigItem(key=item.key, value=item.value, description=item.description)
