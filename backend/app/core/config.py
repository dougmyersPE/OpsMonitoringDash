from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Database
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str

    @property
    def ASYNC_DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def SYNC_DATABASE_URL(self) -> str:
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # Redis
    REDIS_URL: str = "redis://redis:6379"
    CELERY_BROKER_URL: str = "redis://redis:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/1"
    REDBEAT_REDIS_URL: str = "redis://redis:6379/0"

    # Auth
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # External APIs
    PROPHETX_BASE_URL: str = "https://cash.api.prophetx.co/partner"
    PROPHETX_ACCESS_KEY: str
    PROPHETX_SECRET_KEY: str
    SPORTSDATAIO_API_KEY: str
    SPORTSDATAIO_SOCCER_API_KEY: str | None = None
    ODDS_API_KEY: str | None = None
    ODDSBLAZE_API_KEY: str | None = None

    # Admin seed
    ADMIN_EMAIL: str
    ADMIN_PASSWORD: str

    # Alerting
    SLACK_WEBHOOK_URL: str | None = None  # Optional: Slack incoming webhook URL

    # Poll intervals (seconds) — lower during dev/testing, raise before production
    POLL_INTERVAL_PROPHETX: int = 300  # reconciliation-only — ws-consumer handles real-time updates
    POLL_INTERVAL_SPORTS_DATA: int = 30
    POLL_INTERVAL_ODDS_API: int = 600    # conserves free tier (500 calls/month)
    POLL_INTERVAL_ESPN: int = 600
    POLL_INTERVAL_ODDSBLAZE: int = 120  # 2 min — OddsBlaze has no published rate limits

    # WS authority window (seconds) — poll defers to WS within this window (per D-01)
    WS_AUTHORITY_WINDOW_SECONDS: int = 600  # 10 minutes


settings = Settings()
