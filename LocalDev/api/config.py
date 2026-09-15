from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    DATABASE_URL: Optional[str] = None
    JWT_SECRET: str = "local-dev-secret"
    FRONTEND_URL: str = "http://localhost:3000"
    BASE_URL: str = "http://localhost:8001"
    CHECKIN_LINK_TTL_MINUTES: int = 10
    DEV_AUTH_BYPASS: bool = False
    # Shared secret for the Vercel Cron caller (api/cron/api/cron.py). Empty disables
    # every cron endpoint (returns 401) so an unconfigured deploy can't be triggered.
    CRON_SECRET: str = ""
    # Set by Vercel at build/runtime ("production" | "preview" | "development").
    # Empty locally. Drives the production boot guard in api/index.py.
    VERCEL_ENV: str = ""
    # Outbound message delivery: "dry_run" (rows marked simulated, no network) or
    # "twilio" (real sends; requires the TWILIO_* settings below).
    MESSAGE_DELIVERY_MODE: str = "dry_run"
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    # Preferred sender: a Messaging Service ("MG..."), which is what carries the
    # verified toll-free number and Advanced Opt-Out (STOP/HELP) — issue #54.
    TWILIO_MESSAGING_SERVICE_SID: str = ""
    # Fallback sender: bare E.164 number, e.g. +15551234567. Set exactly one of
    # TWILIO_MESSAGING_SERVICE_SID / TWILIO_FROM_NUMBER.
    TWILIO_FROM_NUMBER: str = ""
    # Sentry error reporting. Empty disables Sentry entirely (local/dev default).
    SENTRY_DSN: str = ""

    @property
    def is_production(self) -> bool:
        return self.VERCEL_ENV == "production"

    @property
    def is_deployed(self) -> bool:
        # Preview deploys are public URLs that inherit env vars; they get the
        # same config guard and lockdowns as production.
        return self.VERCEL_ENV in ("production", "preview")

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
