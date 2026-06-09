from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "mysql+pymysql://quicknav:quicknav123@127.0.0.1:3309/quicknavigation"
    cors_origins: str = "*"
    github_webhook_secret: str = "change-me-github-secret"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
