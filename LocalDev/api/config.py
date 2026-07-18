from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    DATABASE_URL: Optional[str] = None
    JWT_SECRET: str = "local-dev-secret"
    FRONTEND_URL: str = "http://localhost:3000"
    BASE_URL: str = "http://localhost:8001"
    CHECKIN_LINK_TTL_MINUTES: int = 10
    DEV_AUTH_BYPASS: bool = False
    # Shared secret for the Vercel Cron caller (api/routes/cron.py). Empty disables
    # the cron endpoint (returns 401) so an unconfigured deploy can't be triggered.
    CRON_SECRET: str = ""
    # Set by Vercel at build/runtime ("production" | "preview" | "development").
    # Empty locally. Drives the production boot guard in api/index.py.
    VERCEL_ENV: str = ""

    @property
    def use_local_db(self) -> bool:
        return bool(self.DATABASE_URL)

    @property
    def is_production(self) -> bool:
        return self.VERCEL_ENV == "production"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
