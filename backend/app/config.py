from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    postgres_user: str = "nexus"
    postgres_password: str = "changeme"
    postgres_db: str = "nexus"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    core_api_secret_key: str = "changeme"

    matrix_server_name: str = "nexus.local"
    matrix_homeserver_url: str = "http://localhost:8008"
    matrix_registration_shared_secret: str = "changeme"

    # TASK-003: Bu adres doğrudan Ollama değil, Tailscale üzerindeki AI Gateway'dir.
    # Gateway Bearer anahtarını doğrular ve yerel Ollama'ya proxy olur.
    ollama_base_url: str = "http://127.0.0.1:8090"
    ollama_api_key: str = ""
    ollama_default_model: str = "qwen2.5:7b"
    ollama_connect_timeout_seconds: float = 5.0
    ollama_read_timeout_seconds: float = 120.0
    ollama_max_retries: int = 2
    ollama_retry_backoff_seconds: float = 0.5
    ollama_model_cache_seconds: float = 30.0

    # TASK-007: AI generation is handled by the separate ai-worker service.
    ai_worker_poll_seconds: float = 0.5
    ai_worker_lease_seconds: int = 300
    ai_worker_max_attempts: int = 3
    ai_worker_retry_backoff_seconds: float = 2.0
    ai_max_pending_jobs_per_user: int = 20
    ai_context_token_budget: int = 3072
    ai_max_output_tokens: int = 1024
    ai_stream_poll_seconds: float = 0.15

    # TASK-010: untrusted plugin code is executed by the dedicated sandbox sidecar.
    # ``local`` exists only for controlled development and must not be used in production.
    plugin_execution_mode: Literal["sandbox", "local"] = "sandbox"
    plugin_sandbox_url: str = "http://plugin-sandbox:8091"
    plugin_sandbox_api_key: str = ""
    plugin_sandbox_timeout_seconds: float = 10.0
    plugin_sandbox_max_payload_bytes: int = 65536
    plugin_sandbox_max_output_bytes: int = 65536

    # TASK-011: coturn long-term REST credentials for WebRTC ICE.
    turn_domain: str = ""
    turn_port: int = 3478
    turn_auth_secret: str = ""
    turn_credential_ttl_seconds: int = 3600

    model_config = SettingsConfigDict(env_file="../.env", env_file_encoding="utf-8", extra="ignore")

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
