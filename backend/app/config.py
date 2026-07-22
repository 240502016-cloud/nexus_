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

    # Hibrit mimari: varsayılan yerel Ollama'ya işaret eder, ama uzak bir "AI işlem
    # sunucusu"na (ör. http://ai-server:11434) yönlendirilebilir. ollama_api_key,
    # aradaki bağlantıyı korumak için bir ters proxy/gateway eklenirse kullanılır -
    # Ollama'nın kendisi API anahtarı istemez.
    ollama_base_url: str = "http://localhost:11434"
    ollama_api_key: str = ""
    ollama_default_model: str = "qwen2.5:7b"

    model_config = SettingsConfigDict(env_file="../.env", env_file_encoding="utf-8", extra="ignore")

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
