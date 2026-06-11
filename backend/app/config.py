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
    omnidb_internal_url: str = "http://127.0.0.1:8081"
    omnidb_public_port: int = 8081
    omnidb_admin_user: str = "admin"
    omnidb_admin_password: str = "admin@123"
    omnidb_mysql_host: str = "127.0.0.1"
    omnidb_db_path: str = ""

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
