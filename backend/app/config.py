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
    matrix_connect_timeout_seconds: float = 3.0
    matrix_read_timeout_seconds: float = 15.0

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
    # Ollama modeli bu süre boyunca bellekte tutar. Varsayılan 5 dakikadır ve
    # ölçüldüğünde soğuk yükleme qwen2.5:7b için 8,1 sn, gpt-oss:20b için 23,2 sn
    # sürüyor — yani boştan sonraki ilk istek modül timeout'larının hepsini aşıyor.
    # Boş bırakılırsa alan isteğe eklenmez ve Ollama kendi varsayılanını kullanır.
    ollama_keep_alive: str = "30m"

    # TASK-007: AI generation is handled by the separate ai-worker service.
    ai_worker_poll_seconds: float = 0.5
    ai_worker_lease_seconds: int = 300
    ai_worker_max_attempts: int = 3
    ai_worker_retry_backoff_seconds: float = 2.0
    ai_max_pending_jobs_per_user: int = 20
    ai_context_token_budget: int = 3072
    ai_max_output_tokens: int = 1024
    ai_stream_poll_seconds: float = 0.15

    # Model seçimi ve timeout'lar geliştirici makinesinde ölçülerek belirlendi
    # (6 Ağustos 2026, RTX 4050 6 GB VRAM + 47 GB RAM):
    #   qwen2.5:7b   27,8 token/sn   soğuk yükleme  8,1 sn
    #   gpt-oss:20b  17,7 token/sn   soğuk yükleme 23,2 sn
    # Her timeout, o özelliğin num_predict bütçesinin tamamı üretilirse geçecek
    # süreyi kapsar. Model 20b'ye VRAM yetmediği için ağırlıklı CPU'da çalışır;
    # geliştirici makinesinde OLLAMA_KEEP_ALIVE=-1 olmalıdır, aksi halde 5 dakika
    # boştan sonraki ilk istek soğuk yükleme süresine takılır.

    # AI Commentator uses a logical role in module code. Until the Gateway supports
    # server-side logical profiles, this setting maps that role to an installed model.
    # Canlı yorum gecikmeye duyarlı olduğu için hızlı model korunur.
    commentator_live_model: str = "qwen2.5:7b"
    commentator_timeout_seconds: float = 5.0
    # Üretim bu süreden uzun sürerse yorum "stale" sayılıp atılır; timeout'tan
    # büyük olmalı, yoksa zamanında biten üretim de çöpe gider.
    commentator_stale_seconds: float = 6.0

    meme_text_model: str = "gpt-oss:20b"
    meme_timeout_seconds: float = 25.0
    generated_media_dir: str = "/srv/generated-media"

    highlight_media_dir: str = "/srv/highlight-media"
    highlight_max_upload_bytes: int = 1024 * 1024 * 1024
    ffmpeg_binary: str = "ffmpeg"
    ffprobe_binary: str = "ffprobe"
    highlight_probe_timeout_seconds: float = 30.0
    highlight_render_timeout_seconds: float = 600.0
    media_worker_poll_seconds: float = 0.5
    # Başlık/etiket üretimi mekanik bir iş; hızlı model yeterli.
    highlight_metadata_model: str = "qwen2.5:7b"
    highlight_metadata_timeout_seconds: float = 10.0
    roast_generate_model: str = "gpt-oss:20b"
    roast_review_model: str = "gpt-oss:20b"
    roast_generate_timeout_seconds: float = 20.0
    roast_review_timeout_seconds: float = 10.0
    board_game_narrator_model: str = "gpt-oss:20b"
    board_game_narrator_timeout_seconds: float = 12.0
    hidden_role_recap_model: str = "gpt-oss:20b"
    hidden_role_recap_timeout_seconds: float = 20.0
    shared_story_model: str = "gpt-oss:20b"
    # num_predict 650 — bu modüldeki en uzun üretim.
    shared_story_timeout_seconds: float = 45.0
    escape_room_host_model: str = "gpt-oss:20b"
    escape_room_host_timeout_seconds: float = 15.0

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
    turn_external_ip: str = ""
    turn_port: int = 3478
    turn_auth_secret: str = ""
    turn_credential_ttl_seconds: int = 3600

    attachment_dir: str = "/srv/attachments"
    attachment_max_bytes: int = 25 * 1024 * 1024

    model_config = SettingsConfigDict(env_file="../.env", env_file_encoding="utf-8", extra="ignore")

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
