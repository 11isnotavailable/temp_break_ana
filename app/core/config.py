from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    OPENAI_API_KEY: str
    OPENAI_API_BASE: str
    MODEL_NAME: str = "deepseek-chat"
    TDI_THRESHOLD: float = 0.15
    STABLE_CYCLES: int = 3
    MAX_EXPERT_TURNS: int = 5

    class Config:
        env_file = ".env"
        extra = "allow"


settings = Settings()
