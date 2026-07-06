from pathlib import Path

from pydantic_settings import BaseSettings

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_REDPANDA_DATA_DIR = _PROJECT_ROOT / "docker" / "redpanda" / "data"


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
    k8s_alarm_monitor_interval_seconds: int = 300
    omnidb_internal_url: str = "http://127.0.0.1:8081"
    omnidb_public_port: int = 8081
    omnidb_admin_user: str = "admin"
    omnidb_admin_password: str = "admin@123"
    omnidb_mysql_host: str = "127.0.0.1"
    omnidb_db_path: str = ""
    sshwifty_public_port: int = 8182
    sshwifty_ssh_host: str = "host.docker.internal"
    redpanda_public_port: int = 8082
    redpanda_kafka_host: str = "host.docker.internal"
    redpanda_config_path: str = str(_REDPANDA_DATA_DIR / "console-config.yml")
    redpanda_clusters_manifest_path: str = str(_REDPANDA_DATA_DIR / "clusters-manifest.yml")
    redpanda_reload_wait_seconds: float = 3.0
    redisinsight_internal_url: str = "http://127.0.0.1:5540"
    redisinsight_public_port: int = 5540
    redisinsight_redis_host: str = "127.0.0.1"
    api_repo_cache_dir: str = str(_PROJECT_ROOT / "data" / "api-repos")

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
