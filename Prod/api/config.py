from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    POSTGRES_URL_NON_POOLING: str = ""
    SUPABASE_JWT_SECRET: str = ""
    FRONTEND_URL: str = "https://fraternity-os.vercel.app"
    FRONTEND_URLS: str = ""
    FRONTEND_ORIGIN_REGEX: str = ""
    BASE_URL: str = "https://guild-os-two.vercel.app"
    CHECKIN_LINK_TTL_MINUTES: int = 10
    CRON_SECRET: str = ""

    class Config:
        env_file = ".env"

    @property
    def cors_origins(self) -> list[str]:
        """Return explicit CORS origins, supporting comma-separated env overrides."""
        items = [self.FRONTEND_URL, *self.FRONTEND_URLS.split(",")]
        return [origin.strip() for origin in items if origin and origin.strip()]


settings = Settings()

if not (settings.SUPABASE_JWT_SECRET or "").strip():
    raise RuntimeError(
        "SUPABASE_JWT_SECRET is missing or whitespace-only. "
        "Set it in the environment or in a .env file next to the API (local dev: copy from "
        "Supabase Project Settings → API → JWT Secret). The API refuses to start without a "
        "non-empty signing key."
    )
