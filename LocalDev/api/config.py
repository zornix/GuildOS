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
    # Shared secret for the Vercel Cron caller (api/routes/cron.py). Empty disables
    # the cron endpoint (returns 401) so an unconfigured deploy can't be triggered.
    CRON_SECRET: str = ""

    @property
    def use_local_db(self) -> bool:
        return bool(self.DATABASE_URL)

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
