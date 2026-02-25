"""
Seed script: creates admin user from env vars if not already present.
Run as: python -m app.seed
"""
import structlog
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app.core.config import settings
from app.core.constants import RoleEnum
from app.core.security import hash_password
from app.db.sync_session import SyncSessionLocal
from app.models.user import User

log = structlog.get_logger()


def seed():
    """Create admin user if it does not exist."""
    try:
        with SyncSessionLocal() as session:
            existing = session.execute(
                select(User).where(User.email == settings.ADMIN_EMAIL)
            ).scalar_one_or_none()

            if existing:
                log.info("seed_skip", reason="admin user already exists", email=settings.ADMIN_EMAIL)
                return

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
    except OperationalError as e:
        log.warning("seed_skip", reason="DB not ready yet", error=str(e))
    except Exception as e:
        log.error("seed_failed", error=str(e))
        raise


if __name__ == "__main__":
    seed()
