"""
notifications.py — In-app notification center API.

NOTIF-01: Lists all system notifications with read/unread state.
All notifications are system-wide (no per-user scoping in v1).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.db.session import get_async_session
from app.models.notification import Notification
from app.schemas.notification import NotificationListResponse, NotificationResponse

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    session: AsyncSession = Depends(get_async_session),
):
    """List all notifications, newest first."""
    result = await session.execute(
        select(Notification).order_by(Notification.created_at.desc()).limit(100)
    )
    notifications = result.scalars().all()
    unread_count = sum(1 for n in notifications if not n.is_read)
    return NotificationListResponse(
        notifications=[NotificationResponse.model_validate(n) for n in notifications],
        unread_count=unread_count,
    )


@router.patch("/mark-all-read", response_model=dict)
async def mark_all_read(
    session: AsyncSession = Depends(get_async_session),
):
    """Mark all unread notifications as read."""
    await session.execute(
        update(Notification).where(Notification.is_read == False).values(is_read=True)  # noqa: E712
    )
    await session.commit()
    return {"marked_read": True}


@router.patch("/{notification_id}/read", response_model=NotificationResponse)
async def mark_notification_read(
    notification_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
):
    """Mark a single notification as read."""
    notification = await session.get(Notification, notification_id)
    if notification is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    notification.is_read = True
    await session.commit()
    await session.refresh(notification)
    return NotificationResponse.model_validate(notification)
