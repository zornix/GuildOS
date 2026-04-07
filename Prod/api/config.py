from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://fraternityos:localdev@localhost:5434/fraternityos"
    JWT_SECRET: str = "local-dev-secret"
    FRONTEND_URL: str = "http://localhost:3000"
    BASE_URL: str = "http://localhost:8001"
    CHECKIN_LINK_TTL_MINUTES: int = 10

    class Config:
        env_file = ".env"


settings = Settings()
