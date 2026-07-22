from __future__ import annotations

import logging
import json
import threading
import time
from collections.abc import Callable
from typing import Any

import requests

from app.config import settings

logger = logging.getLogger(__name__)


class OllamaError(RuntimeError):
    """AI Gateway/Ollama zincirindeki bütün kontrollü hataların tabanı."""


class OllamaGatewayUnavailableError(OllamaError):
    pass


class OllamaGatewayTimeoutError(OllamaError):
    pass


class OllamaGatewayAuthenticationError(OllamaError):
    pass


class OllamaModelNotFoundError(OllamaError):
    pass


# Küçük yerel modeller (ör. qwen2.5:7b) sistem promptu olmadan tutarsız/uydurma cevaplar
# verebiliyor; bu varsayılan, cevap kalitesini ücretsiz bir şekilde biraz iyileştirir.
DEFAULT_SYSTEM_PROMPT = (
    "Sen Nexus platformunun yardımsever, Türkçe konuşan bir AI asistanısın. Kısa ve net "
    "cevaplar ver. Emin olmadığın konularda tahmin yürütüp uydurma bilgi verme - "
    "bilmediğini açıkça söyle. Kullanıcı Türkçe karakter kullanmadan yazsa bile "
    "(ör. 'turkiyenin' yerine 'türkiye'nin') niyetini anlamaya çalış."
)

_RETRYABLE_STATUS_CODES = {429, 502, 503, 504}


class OllamaClient:
    """Nexus Core API'den AI Gateway'e konuşan istemci.

    `base_url` doğrudan Ollama adresi değil, TASK-001'deki AI Gateway adresidir. Gateway
    `/ai/health`, `/api/tags` ve `/api/chat` sözleşmelerini sunar. Bearer anahtarı her
    istekte zorunludur; Ollama'ya aktarılması gateway tarafından engellenir.
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        *,
        connect_timeout: float | None = None,
        read_timeout: float | None = None,
        max_retries: int | None = None,
        retry_backoff: float | None = None,
        model_cache_seconds: float | None = None,
        http_client: Any = requests,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.api_key = api_key if api_key is not None else settings.ollama_api_key
        self.connect_timeout = (
            connect_timeout if connect_timeout is not None else settings.ollama_connect_timeout_seconds
        )
        self.read_timeout = read_timeout if read_timeout is not None else settings.ollama_read_timeout_seconds
        self.max_retries = max_retries if max_retries is not None else settings.ollama_max_retries
        self.retry_backoff = (
            retry_backoff if retry_backoff is not None else settings.ollama_retry_backoff_seconds
        )
        self.model_cache_seconds = (
            model_cache_seconds if model_cache_seconds is not None else settings.ollama_model_cache_seconds
        )
        self._http = http_client
        self._sleep = sleep
        self._clock = clock
        self._model_cache: tuple[str, ...] = ()
        self._model_cache_expires_at = 0.0
        self._cache_lock = threading.Lock()

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise OllamaGatewayAuthenticationError(
                "AI Gateway API anahtarı ayarlanmamış (OLLAMA_API_KEY)"
            )
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    @staticmethod
    def _response_detail(response: Any) -> str:
        try:
            payload = response.json()
            detail = payload.get("detail") or payload.get("error")
            if detail:
                return str(detail)[:300]
        except (ValueError, AttributeError, TypeError):
            pass
        return str(getattr(response, "text", ""))[:300]

    def _raise_for_response(self, response: Any, path: str) -> None:
        status = int(response.status_code)
        detail = self._response_detail(response)
        if status in (401, 403):
            raise OllamaGatewayAuthenticationError(
                f"AI Gateway kimlik doğrulamasını reddetti (HTTP {status})"
            )
        if status == 504:
            raise OllamaGatewayTimeoutError("AI Gateway/Ollama isteği zaman aşımına uğradı")
        if status in (429, 502, 503):
            raise OllamaGatewayUnavailableError(
                f"AI Gateway geçici olarak kullanılamıyor (HTTP {status}): {detail}"
            )
        if status == 404 and path == "/api/chat":
            raise OllamaModelNotFoundError(f"AI modeli bulunamadı: {detail}")
        raise OllamaError(f"AI Gateway isteği başarısız (HTTP {status}): {detail}")

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
        read_timeout: float | None = None,
        retry_read_timeout: bool,
    ):
        attempts = max(0, self.max_retries) + 1
        timeout = (self.connect_timeout, read_timeout or self.read_timeout)

        for attempt in range(attempts):
            try:
                response = self._http.request(
                    method,
                    f"{self.base_url}{path}",
                    headers=self._headers(),
                    json=json,
                    timeout=timeout,
                )
            except requests.ReadTimeout as exc:
                if retry_read_timeout and attempt + 1 < attempts:
                    self._wait_before_retry(attempt, path, "read timeout")
                    continue
                raise OllamaGatewayTimeoutError("AI Gateway/Ollama isteği zaman aşımına uğradı") from exc
            except requests.ConnectTimeout as exc:
                if attempt + 1 < attempts:
                    self._wait_before_retry(attempt, path, "connect timeout")
                    continue
                raise OllamaGatewayTimeoutError("AI Gateway bağlantısı zaman aşımına uğradı") from exc
            except requests.ConnectionError as exc:
                if attempt + 1 < attempts:
                    self._wait_before_retry(attempt, path, "connection error")
                    continue
                raise OllamaGatewayUnavailableError(f"AI Gateway'e ulaşılamadı ({self.base_url})") from exc
            except requests.RequestException as exc:
                raise OllamaGatewayUnavailableError(f"AI Gateway isteği gönderilemedi: {exc}") from exc

            if response.ok:
                return response

            retry_status = response.status_code in _RETRYABLE_STATUS_CODES
            # Chat read-timeout/504 sonrasında yeniden denemek aynı üretimi iki kez başlatabilir.
            # Bağlantı kurulmuş ve gateway 504 dönmüşse bunu tekrar etmeyiz; 429/502/503 ise
            # geçici upstream/gateway hatası kabul edilip sınırlı şekilde yeniden denenir.
            if path == "/api/chat" and response.status_code == 504:
                retry_status = False
            if retry_status and attempt + 1 < attempts:
                self._wait_before_retry(attempt, path, f"HTTP {response.status_code}")
                continue

            self._raise_for_response(response, path)

        raise OllamaGatewayUnavailableError("AI Gateway isteği tamamlanamadı")

    def _wait_before_retry(self, attempt: int, path: str, reason: str) -> None:
        delay = max(0.0, self.retry_backoff) * (2**attempt)
        logger.warning(
            "AI Gateway isteği yeniden denenecek: path=%s reason=%s attempt=%s delay=%.2fs",
            path,
            reason,
            attempt + 1,
            delay,
        )
        if delay:
            self._sleep(delay)

    @staticmethod
    def _json(response: Any, operation: str) -> dict:
        try:
            payload = response.json()
        except ValueError as exc:
            raise OllamaError(f"AI Gateway {operation} için geçersiz JSON döndürdü") from exc
        if not isinstance(payload, dict):
            raise OllamaError(f"AI Gateway {operation} için geçersiz yanıt döndürdü")
        return payload

    def health(self, *, force_refresh: bool = True) -> dict[str, object]:
        """Gateway ve arkasındaki Ollama durumunu/model listesini döndürür."""
        models = self.available_models(force_refresh=force_refresh)
        return {"status": "online", "models": models}

    def available_models(self, *, force_refresh: bool = False) -> list[str]:
        now = self._clock()
        with self._cache_lock:
            if not force_refresh and now < self._model_cache_expires_at:
                return list(self._model_cache)

        response = self._request(
            "GET",
            "/ai/health",
            read_timeout=min(self.read_timeout, 15.0),
            retry_read_timeout=True,
        )
        payload = self._json(response, "health kontrolü")
        if payload.get("status") != "online" or not isinstance(payload.get("models"), list):
            raise OllamaGatewayUnavailableError("AI Gateway/Ollama online değil")

        models = [str(model) for model in payload["models"] if isinstance(model, str) and model]
        with self._cache_lock:
            self._model_cache = tuple(models)
            self._model_cache_expires_at = self._clock() + max(0.0, self.model_cache_seconds)
        return models

    def ensure_model_available(self, model: str, *, force_refresh: bool = False) -> None:
        models = self.available_models(force_refresh=force_refresh)
        if model not in models:
            available = ", ".join(models) if models else "yok"
            raise OllamaModelNotFoundError(
                f"'{model}' modeli AI sunucusunda kurulu değil. Kurulu modeller: {available}"
            )

    def list_models(self) -> list[dict]:
        response = self._request(
            "GET",
            "/api/tags",
            read_timeout=min(self.read_timeout, 15.0),
            retry_read_timeout=True,
        )
        payload = self._json(response, "model listesi")
        models = payload.get("models", [])
        if not isinstance(models, list):
            raise OllamaError("AI Gateway geçersiz model listesi döndürdü")
        return [model for model in models if isinstance(model, dict)]

    def chat(
        self,
        model: str,
        messages: list[dict],
        timeout: float | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict:
        """Modeli doğrular ve sohbeti AI Gateway üzerinden Ollama'ya gönderir."""
        self.ensure_model_available(model)
        payload: dict[str, Any] = {"model": model, "messages": messages, "stream": False}
        if options:
            payload["options"] = options
        response = self._request(
            "POST",
            "/api/chat",
            json=payload,
            read_timeout=timeout or self.read_timeout,
            retry_read_timeout=False,
        )
        return self._json(response, "sohbet")

    def chat_stream(
        self,
        model: str,
        messages: list[dict],
        *,
        timeout: float | None = None,
        options: dict[str, Any] | None = None,
    ):
        """Yield Ollama NDJSON chunks without buffering the complete response."""
        self.ensure_model_available(model)
        payload: dict[str, Any] = {"model": model, "messages": messages, "stream": True}
        if options:
            payload["options"] = options
        try:
            response = self._http.request(
                "POST",
                f"{self.base_url}/api/chat",
                headers=self._headers(),
                json=payload,
                timeout=(self.connect_timeout, timeout or self.read_timeout),
                stream=True,
            )
        except requests.ConnectTimeout as exc:
            raise OllamaGatewayTimeoutError("AI Gateway bağlantısı zaman aşımına uğradı") from exc
        except requests.ReadTimeout as exc:
            raise OllamaGatewayTimeoutError("AI Gateway/Ollama isteği zaman aşımına uğradı") from exc
        except requests.ConnectionError as exc:
            raise OllamaGatewayUnavailableError(f"AI Gateway'e ulaşılamadı ({self.base_url})") from exc
        except requests.RequestException as exc:
            raise OllamaGatewayUnavailableError(f"AI Gateway isteği gönderilemedi: {exc}") from exc

        if not response.ok:
            try:
                self._raise_for_response(response, "/api/chat")
            finally:
                response.close()

        try:
            for raw_line in response.iter_lines(decode_unicode=True):
                if not raw_line:
                    continue
                if isinstance(raw_line, bytes):
                    raw_line = raw_line.decode("utf-8")
                try:
                    payload = json.loads(raw_line)
                except (TypeError, ValueError) as exc:
                    raise OllamaError("AI Gateway streaming yanıtında geçersiz JSON") from exc
                if not isinstance(payload, dict):
                    continue
                message = payload.get("message")
                chunk = message.get("content", "") if isinstance(message, dict) else ""
                yield str(chunk) if chunk else "", payload
        except requests.ReadTimeout as exc:
            raise OllamaGatewayTimeoutError("AI Gateway/Ollama streaming zaman aşımına uğradı") from exc
        finally:
            response.close()


ollama_client = OllamaClient()
