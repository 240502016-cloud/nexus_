from __future__ import annotations

import json
import unittest

import httpx
from pydantic import SecretStr

from gateway.config import Settings, parse_networks
from gateway.main import create_app

API_KEY = "test-key-that-is-at-least-thirty-two-characters"


def test_settings(**overrides) -> Settings:
    values = {
        "ai_gateway_api_key": SecretStr(API_KEY),
        "ai_gateway_allowed_networks": "10.8.0.0/24",
        "ollama_base_url": "http://ollama.test:11434",
    }
    values.update(overrides)
    return Settings(**values)


class GatewayApiTests(unittest.IsolatedAsyncioTestCase):
    async def _request(
        self,
        transport_handler,
        method: str,
        path: str,
        *,
        client_host: str = "10.8.0.12",
        **kwargs,
    ) -> httpx.Response:
        app = create_app(test_settings(), transport=httpx.MockTransport(transport_handler))
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app, client=(client_host, 54321))
            async with httpx.AsyncClient(transport=transport, base_url="http://gateway.test") as client:
                return await client.request(method, path, **kwargs)

    async def test_health_returns_installed_model_names(self):
        def upstream(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/api/tags")
            return httpx.Response(
                200,
                json={"models": [{"name": "llama3:latest"}, {"name": "mistral:latest"}]},
            )

        response = await self._request(
            upstream,
            "GET",
            "/ai/health",
            headers={"Authorization": f"Bearer {API_KEY}"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "online", "models": ["llama3:latest", "mistral:latest"]})

    async def test_missing_api_key_is_rejected_before_ollama(self):
        def upstream(_request: httpx.Request) -> httpx.Response:
            raise AssertionError("Ollama should not be called")

        response = await self._request(upstream, "GET", "/ai/health")
        self.assertEqual(response.status_code, 401)

    async def test_ip_outside_vpn_whitelist_is_rejected_before_api_key_check(self):
        def upstream(_request: httpx.Request) -> httpx.Response:
            raise AssertionError("Ollama should not be called")

        response = await self._request(
            upstream,
            "GET",
            "/ai/health",
            client_host="192.168.50.20",
            headers={"Authorization": f"Bearer {API_KEY}"},
        )
        self.assertEqual(response.status_code, 403)

    async def test_health_reports_offline_when_ollama_is_unhealthy(self):
        def upstream(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"error": "upstream failure"})

        response = await self._request(
            upstream,
            "GET",
            "/ai/health",
            headers={"Authorization": f"Bearer {API_KEY}"},
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["status"], "offline")

    async def test_chat_is_forwarded_without_gateway_authorization_header(self):
        payload = {"model": "qwen2.5:7b", "messages": [{"role": "user", "content": "merhaba"}], "stream": False}

        def upstream(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/api/chat")
            self.assertNotIn("authorization", request.headers)
            self.assertEqual(json.loads(request.content), payload)
            return httpx.Response(200, json={"message": {"role": "assistant", "content": "Merhaba!"}})

        response = await self._request(
            upstream,
            "POST",
            "/api/chat",
            headers={"Authorization": f"Bearer {API_KEY}"},
            json=payload,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["message"]["content"], "Merhaba!")


class ConfigurationTests(unittest.TestCase):
    def test_cidr_parser_accepts_ipv4_and_ipv6(self):
        networks = parse_networks("10.8.0.0/24, fd00:1234::/64")
        self.assertEqual(len(networks), 2)

    def test_short_api_key_fails_runtime_validation(self):
        settings = test_settings(ai_gateway_api_key=SecretStr("short"))
        with self.assertRaises(RuntimeError):
            settings.validate_runtime()

    def test_example_api_key_cannot_start_gateway(self):
        settings = test_settings(ai_gateway_api_key=SecretStr("replace-with-a-long-random-secret"))
        with self.assertRaises(RuntimeError):
            settings.validate_runtime()


if __name__ == "__main__":
    unittest.main()
