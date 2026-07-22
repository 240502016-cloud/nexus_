from __future__ import annotations

from ipaddress import IPv4Network, IPv6Network, ip_network

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

Network = IPv4Network | IPv6Network


def parse_networks(value: str) -> tuple[Network, ...]:
    """Parse a comma-separated list of IPv4/IPv6 CIDR networks."""
    networks: list[Network] = []
    for item in value.split(","):
        candidate = item.strip()
        if candidate:
            networks.append(ip_network(candidate, strict=False))
    return tuple(networks)


class Settings(BaseSettings):
    ai_gateway_api_key: SecretStr = SecretStr("")
    ai_gateway_allowed_networks: str = "127.0.0.1/32,::1/128"
    ai_gateway_trusted_proxies: str = ""

    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_connect_timeout_seconds: float = 5.0
    ollama_read_timeout_seconds: float = 120.0
    ai_gateway_max_request_bytes: int = 1_048_576

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def allowed_networks(self) -> tuple[Network, ...]:
        return parse_networks(self.ai_gateway_allowed_networks)

    @property
    def trusted_proxies(self) -> tuple[Network, ...]:
        return parse_networks(self.ai_gateway_trusted_proxies)

    def validate_runtime(self) -> None:
        api_key = self.ai_gateway_api_key.get_secret_value()
        if len(api_key) < 32 or api_key == "replace-with-a-long-random-secret":
            raise RuntimeError("AI_GATEWAY_API_KEY en az 32 karakterlik rastgele bir değer olmalıdır")
        if not self.allowed_networks:
            raise RuntimeError("AI_GATEWAY_ALLOWED_NETWORKS en az bir CIDR ağı içermelidir")
        if self.ai_gateway_max_request_bytes <= 0:
            raise RuntimeError("AI_GATEWAY_MAX_REQUEST_BYTES sıfırdan büyük olmalıdır")
