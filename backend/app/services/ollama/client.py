from __future__ import annotations

import requests

from app.config import settings


class OllamaError(RuntimeError):
    pass


# Küçük yerel modeller (ör. qwen2.5:7b) sistem promptu olmadan tutarsız/uydurma cevaplar
# verebiliyor; bu varsayılan, cevap kalitesini ücretsiz bir şekilde biraz iyileştirir.
# Gerçek kalite farkı büyük/ticari modellere göre hâlâ belirgindir - bu bir sınır, hata değil.
DEFAULT_SYSTEM_PROMPT = (
    "Sen Nexus platformunun yardımsever, Türkçe konuşan bir AI asistanısın. Kısa ve net "
    "cevaplar ver. Emin olmadığın konularda tahmin yürütüp uydurma bilgi verme - "
    "bilmediğini açıkça söyle. Kullanıcı Türkçe karakter kullanmadan yazsa bile "
    "(ör. 'turkiyenin' yerine 'türkiye'nin') niyetini anlamaya çalış."
)


class OllamaClient:
    """Ollama'nın HTTP API'sine konuşan ince istemci.

    base_url yapılandırılabilir: hibrit mimaride bu, ayrı bir "AI işlem sunucusu"ndaki
    (ör. arkadaş bilgisayarından erişilebilen bir makine) Ollama'ya işaret edebilir.
    api_key, Ollama'nın kendisi için gerekmez (yerel/ücretsiz) - sadece araya bir
    gateway/reverse-proxy konursa (kimlik doğrulama için) kullanılır.
    """

    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.api_key = api_key if api_key is not None else settings.ollama_api_key

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def list_models(self) -> list[dict]:
        try:
            response = requests.get(f"{self.base_url}/api/tags", headers=self._headers(), timeout=10)
        except requests.RequestException as exc:
            raise OllamaError(f"Ollama'ya ulaşılamadı ({self.base_url}): {exc}") from exc
        if not response.ok:
            raise OllamaError(f"Model listesi alınamadı: {response.status_code} {response.text}")
        return response.json().get("models", [])

    def chat(self, model: str, messages: list[dict], timeout: float = 120.0) -> dict:
        """messages: [{"role": "user"|"assistant"|"system", "content": "..."}], eskiden
        yeniye sıralı - context yönetimi burada değil, çağıran tarafta yapılır."""
        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                headers=self._headers(),
                json={"model": model, "messages": messages, "stream": False},
                timeout=timeout,
            )
        except requests.RequestException as exc:
            raise OllamaError(f"Ollama'ya ulaşılamadı ({self.base_url}): {exc}") from exc
        if not response.ok:
            raise OllamaError(f"Ollama isteği başarısız: {response.status_code} {response.text}")
        return response.json()


ollama_client = OllamaClient()
