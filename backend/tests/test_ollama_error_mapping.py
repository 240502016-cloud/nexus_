from __future__ import annotations

import unittest

from app.services.ollama.client import (
    OllamaError,
    OllamaGatewayAuthenticationError,
    OllamaGatewayTimeoutError,
    OllamaGatewayUnavailableError,
    OllamaModelNotFoundError,
)
from app.services.ollama.requests import _ollama_http_exception


class OllamaHttpErrorMappingTests(unittest.TestCase):
    def test_model_error_maps_to_422(self):
        self.assertEqual(_ollama_http_exception(OllamaModelNotFoundError("missing")).status_code, 422)

    def test_authentication_error_maps_to_server_side_502(self):
        self.assertEqual(
            _ollama_http_exception(OllamaGatewayAuthenticationError("bad gateway key")).status_code,
            502,
        )

    def test_unavailable_error_maps_to_503(self):
        self.assertEqual(
            _ollama_http_exception(OllamaGatewayUnavailableError("offline")).status_code,
            503,
        )

    def test_timeout_error_maps_to_504(self):
        self.assertEqual(_ollama_http_exception(OllamaGatewayTimeoutError("slow")).status_code, 504)

    def test_generic_upstream_error_maps_to_502(self):
        self.assertEqual(_ollama_http_exception(OllamaError("bad response")).status_code, 502)


if __name__ == "__main__":
    unittest.main()
