from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # 这里的变量名要和 .env 一致，Pydantic 会自动映射
    OPENAI_API_KEY: str
    OPENAI_API_BASE: str
    MODEL_NAME: str = "deepseek-chat"
    
    TDI_THRESHOLD: float = 0.15
    STABLE_CYCLES: int = 3

    class Config:
        env_file = ".env"
        # 允许额外变量
        extra = "allow"

settings = Settings()