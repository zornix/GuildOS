from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    POSTGRES_URL: str = ""
    SUPABASE_JWT_SECRET: str = ""
    FRONTEND_URL: str = "https://fraternity-os.vercel.app"
    BASE_URL: str = "https://guild-os-two.vercel.app/api"
    CHECKIN_LINK_TTL_MINUTES: int = 10

    class Config:
        env_file = ".env"


settings = Settings()
