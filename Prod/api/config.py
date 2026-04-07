from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://postgres:[YOUR-PASSWORD]@db.rcdertwcsodstmwfygpz.supabase.co:5432/postgres"
    JWT_SECRET: str = "QPLOnmefgLAvU8yo3LMXUQuqYrX1A2pJGPo4xzeGx5F"
    FRONTEND_URL: str = "https://fraternity-os.vercel.app"
    BASE_URL: str = "https://guild-os-blush.vercel.app"
    CHECKIN_LINK_TTL_MINUTES: int = 10

    class Config:
        env_file = ".env"


settings = Settings()
