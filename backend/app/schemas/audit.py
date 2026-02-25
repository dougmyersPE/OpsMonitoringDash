from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AuditLogEntry(BaseModel):
    id: UUID
    timestamp: datetime
    action_type: str
    actor: str
    entity_type: str | None
    entity_id: UUID | None
    before_state: dict | None
    after_state: dict | None
    result: str
    error_message: str | None
    model_config = ConfigDict(from_attributes=True)


class AuditLogPage(BaseModel):
    total: int
    page: int
    per_page: int
    entries: list[AuditLogEntry]
