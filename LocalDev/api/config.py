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
    # Ops shared secret for POST /api/chapters (api/chapters/auth.py). Empty just
    # means the ops path is unavailable; the rate-limited bootstrap path stays on.
    PLATFORM_SECRET: str = ""
    # Set by Vercel at build/runtime ("production" | "preview" | "development").
    # Empty locally. Drives the production boot guard in api/index.py.
    VERCEL_ENV: str = ""
    # Outbound message delivery: "dry_run" (rows marked simulated, no network) or
    # "twilio" (real sends; requires the TWILIO_* settings below).
    MESSAGE_DELIVERY_MODE: str = "dry_run"
    # Trusted reverse-proxy hops appending to X-Forwarded-For. Proxies append the
    # peer at the RIGHT, so the real client is the Nth entry from the right; the
    # leftmost entry is whatever the client sent. 1 = Vercel's edge. Raise only
    # if a proxy is added in front of it.
    TRUSTED_PROXY_HOPS: int = 1
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    # Preferred sender: a Messaging Service ("MG..."), which is what carries the
    # verified toll-free number and Advanced Opt-Out (STOP/HELP) — issue #54.
    TWILIO_MESSAGING_SERVICE_SID: str = ""
    # Fallback sender: bare E.164 number, e.g. +15551234567. Set exactly one of
    # TWILIO_MESSAGING_SERVICE_SID / TWILIO_FROM_NUMBER.
    TWILIO_FROM_NUMBER: str = ""
    # Outbound email — everything automatic (ADR-0005). "dry_run" (rows marked
    # simulated, no network) or "smtp" (real sends via SMTP_*/EMAIL_FROM below).
    EMAIL_DELIVERY_MODE: str = "dry_run"
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587  # STARTTLS
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""  # a Google app password, not the account password
    # RFC 5322 sender, e.g. 'GuildOS <ops@chapter.org>'. Gmail rewrites this to
    # SMTP_USER unless the address is a verified "send mail as" alias.
    EMAIL_FROM: str = ""
    EMAIL_REPLY_TO: str = ""

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
