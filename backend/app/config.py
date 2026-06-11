from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "mysql+pymysql://quicknav:quicknav123@127.0.0.1:3309/quicknavigation"
    cors_origins: str = "*"
    github_webhook_secret: str = "change-me-github-secret"
    github_token: str = ""
    gitlab_webhook_secret: str = "change-me-gitlab-secret"
    gitlab_token: str = ""
    gitlab_base_url: str = "https://gitlab.com"
    public_webhook_base_url: str = ""
    schema_monitor_interval_seconds: int = 300

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
