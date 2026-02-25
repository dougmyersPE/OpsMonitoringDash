"""
Seed script — creates admin user on first startup if it doesn't exist.
Run via: python -m app.seed
"""
import structlog
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app.core.config import settings
from app.core.constants import RoleEnum
from app.db.sync_session import SyncSessionLocal

log = structlog.get_logger()


def seed():
    """Create admin user if it does not exist."""
    try:
        # Import here to avoid circular imports at module load time
        from app.models.user import User  # noqa: F401

        with SyncSessionLocal() as session:
            existing = session.execute(
                select(User).where(User.email == settings.ADMIN_EMAIL)
            ).scalar_one_or_none()

            if existing:
                log.info("seed", message="Admin user already exists, skipping seed")
                return

            # Lazy import to avoid loading pwdlib at module level unnecessarily
            from pwdlib import PasswordHash
            from pwdlib.hashers.bcrypt import BcryptHasher

            pwd_hasher = PasswordHash([BcryptHasher()])
            admin = User(
                email=settings.ADMIN_EMAIL,
                password_hash=pwd_hasher.hash(settings.ADMIN_PASSWORD),
                role=RoleEnum.admin,
                name="Admin",
            )
            session.add(admin)
            session.commit()
            log.info("seed", message="Admin user created", email=settings.ADMIN_EMAIL)
    except OperationalError as e:
        # Tables may not exist yet — Alembic runs after this; safe to ignore
        log.warning("seed", message="Seed skipped — DB not ready yet", error=str(e))
    except Exception as e:
        log.error("seed", message="Seed failed", error=str(e))
        raise


if __name__ == "__main__":
    seed()
