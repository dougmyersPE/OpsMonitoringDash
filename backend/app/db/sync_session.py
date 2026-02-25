from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

sync_engine = create_engine(
    settings.SYNC_DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
)

SyncSessionLocal = sessionmaker(sync_engine, expire_on_commit=False)


def get_sync_session() -> Generator[Session, None, None]:
    with SyncSessionLocal() as session:
        yield session
