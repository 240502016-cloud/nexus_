from __future__ import annotations

import unittest

import requests

from app.services.ollama.client import (
    OllamaClient,
    OllamaGatewayAuthenticationError,
    OllamaGatewayTimeoutError,
    OllamaModelNotFoundError,
)


class FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 400

    def json(self) -> dict:
        return self._payload


class ScriptedHttpClient:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls: list[dict] = []

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def make_client(outcomes, **overrides):
    http = ScriptedHttpClient(outcomes)
    sleeps: list[float] = []
    values = {
        "base_url": "http://100.90.0.20:8090",
        "api_key": "gateway-secret",
        "connect_timeout": 2,
        "read_timeout": 30,
        "max_retries": 2,
        "retry_backoff": 0.25,
        "model_cache_seconds": 30,
        "http_client": http,
        "sleep": sleeps.append,
    }
    values.update(overrides)
    return OllamaClient(**values), http, sleeps


class OllamaGatewayClientTests(unittest.TestCase):
    def test_health_uses_gateway_and_bearer_key(self):
        client, http, _ = make_client(
            [FakeResponse(200, {"status": "online", "models": ["qwen2.5:7b"]})]
        )

        health = client.health(force_refresh=True)

        self.assertEqual(health, {"status": "online", "models": ["qwen2.5:7b"]})
        self.assertEqual(http.calls[0]["url"], "http://100.90.0.20:8090/ai/health")
        self.assertEqual(http.calls[0]["headers"]["Authorization"], "Bearer gateway-secret")

    def test_chat_checks_model_then_proxies_to_gateway(self):
        client, http, _ = make_client(
            [
                FakeResponse(200, {"status": "online", "models": ["qwen2.5:7b"]}),
                FakeResponse(200, {"message": {"role": "assistant", "content": "Merhaba"}}),
            ]
        )

        result = client.chat("qwen2.5:7b", [{"role": "user", "content": "Merhaba"}])

        self.assertEqual(result["message"]["content"], "Merhaba")
        self.assertEqual([call["url"] for call in http.calls], [
            "http://100.90.0.20:8090/ai/health",
            "http://100.90.0.20:8090/api/chat",
        ])
        self.assertFalse(http.calls[1]["json"]["stream"])

    def test_missing_model_stops_before_chat_request(self):
        client, http, _ = make_client(
            [FakeResponse(200, {"status": "online", "models": ["mistral:latest"]})]
        )

        with self.assertRaises(OllamaModelNotFoundError):
            client.chat("qwen2.5:7b", [{"role": "user", "content": "Merhaba"}])

        self.assertEqual(len(http.calls), 1)

    def test_connection_error_is_retried_with_exponential_backoff(self):
        client, http, sleeps = make_client(
            [
                requests.ConnectionError("offline"),
                requests.ConnectionError("offline"),
                FakeResponse(200, {"status": "online", "models": ["qwen2.5:7b"]}),
            ]
        )

        self.assertEqual(client.available_models(force_refresh=True), ["qwen2.5:7b"])
        self.assertEqual(len(http.calls), 3)
        self.assertEqual(sleeps, [0.25, 0.5])

    def test_temporary_chat_gateway_error_is_retried(self):
        client, http, sleeps = make_client(
            [
                FakeResponse(200, {"status": "online", "models": ["qwen2.5:7b"]}),
                FakeResponse(503, {"detail": "Ollama unavailable"}),
                FakeResponse(200, {"message": {"role": "assistant", "content": "ok"}}),
            ],
            max_retries=1,
        )

        result = client.chat("qwen2.5:7b", [{"role": "user", "content": "test"}])

        self.assertEqual(result["message"]["content"], "ok")
        self.assertEqual(len(http.calls), 3)
        self.assertEqual(sleeps, [0.25])

    def test_gateway_authentication_error_is_not_retried(self):
        client, http, sleeps = make_client([FakeResponse(401, {"detail": "invalid key"})])

        with self.assertRaises(OllamaGatewayAuthenticationError):
            client.health(force_refresh=True)

        self.assertEqual(len(http.calls), 1)
        self.assertEqual(sleeps, [])

    def test_chat_read_timeout_is_not_retried_to_avoid_duplicate_generation(self):
        client, http, sleeps = make_client(
            [
                FakeResponse(200, {"status": "online", "models": ["qwen2.5:7b"]}),
                requests.ReadTimeout("slow model"),
            ]
        )

        with self.assertRaises(OllamaGatewayTimeoutError):
            client.chat("qwen2.5:7b", [{"role": "user", "content": "test"}])

        self.assertEqual(len(http.calls), 2)
        self.assertEqual(sleeps, [])


if __name__ == "__main__":
    unittest.main()
