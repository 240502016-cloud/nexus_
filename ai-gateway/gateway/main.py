from __future__ import annotations

from contextlib import asynccontextmanager
import json
from typing import AsyncIterator

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel

from gateway.config import Settings
from gateway.security import address_in_networks, api_key_is_valid, extract_api_key, resolve_client_ip


class HealthResponse(BaseModel):
    status: str
    models: list[str]


def _upstream_error(exc: Exception) -> JSONResponse:
    if isinstance(exc, httpx.TimeoutException):
        return JSONResponse(status_code=504, content={"detail": "Ollama isteği zaman aşımına uğradı"})
    return JSONResponse(status_code=502, content={"detail": "Ollama sunucusuna ulaşılamadı"})


def _forward_response(response: httpx.Response) -> Response:
    content_type = response.headers.get("content-type", "application/json")
    return Response(
        content=response.content,
        status_code=response.status_code,
        headers={"Content-Type": content_type},
    )


def create_app(settings: Settings | None = None, transport: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    gateway_settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        gateway_settings.validate_runtime()
        timeout = httpx.Timeout(
            connect=gateway_settings.ollama_connect_timeout_seconds,
            read=gateway_settings.ollama_read_timeout_seconds,
            write=10.0,
            pool=5.0,
        )
        async with httpx.AsyncClient(
            base_url=gateway_settings.ollama_base_url.rstrip("/"),
            timeout=timeout,
            transport=transport,
        ) as client:
            app.state.ollama_client = client
            yield

    app = FastAPI(
        title="Nexus AI Gateway",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.settings = gateway_settings

    @app.middleware("http")
    async def enforce_gateway_access(request: Request, call_next):
        client_ip = resolve_client_ip(request, gateway_settings.trusted_proxies)
        if client_ip is None or not address_in_networks(client_ip, gateway_settings.allowed_networks):
            return JSONResponse(status_code=403, content={"detail": "Bu IP adresine izin verilmiyor"})
        if not api_key_is_valid(extract_api_key(request), gateway_settings):
            return JSONResponse(
                status_code=401,
                content={"detail": "Geçersiz veya eksik API anahtarı"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        return await call_next(request)

    @app.get("/ai/health", response_model=HealthResponse)
    async def ai_health(request: Request):
        client: httpx.AsyncClient = request.app.state.ollama_client
        try:
            response = await client.get("/api/tags")
        except httpx.HTTPError as exc:
            error = _upstream_error(exc)
            error.status_code = 503
            return error

        if not response.is_success:
            return JSONResponse(
                status_code=503,
                content={"status": "offline", "models": [], "detail": f"Ollama HTTP {response.status_code}"},
            )

        try:
            payload = response.json()
        except ValueError:
            return JSONResponse(
                status_code=503,
                content={"status": "offline", "models": [], "detail": "Ollama geçersiz JSON döndürdü"},
            )
        models = [
            str(model.get("name") or model.get("model"))
            for model in payload.get("models", [])
            if model.get("name") or model.get("model")
        ]
        return HealthResponse(status="online", models=models)

    @app.get("/api/tags")
    async def proxy_tags(request: Request):
        client: httpx.AsyncClient = request.app.state.ollama_client
        try:
            response = await client.get("/api/tags")
        except httpx.HTTPError as exc:
            return _upstream_error(exc)
        return _forward_response(response)

    @app.post("/api/chat")
    async def proxy_chat(request: Request):
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > gateway_settings.ai_gateway_max_request_bytes:
                    return JSONResponse(status_code=413, content={"detail": "İstek gövdesi çok büyük"})
            except ValueError:
                return JSONResponse(status_code=400, content={"detail": "Geçersiz Content-Length"})

        body = await request.body()
        if len(body) > gateway_settings.ai_gateway_max_request_bytes:
            return JSONResponse(status_code=413, content={"detail": "İstek gövdesi çok büyük"})

        try:
            stream_requested = bool(json.loads(body).get("stream", False))
        except (TypeError, ValueError):
            return JSONResponse(status_code=400, content={"detail": "Geçersiz JSON"})

        if stream_requested:
            stream_context = request.app.state.ollama_client.stream(
                "POST",
                "/api/chat",
                content=body,
                headers={"Content-Type": "application/json"},
            )
            try:
                upstream = await stream_context.__aenter__()
            except httpx.HTTPError as exc:
                await stream_context.__aexit__(type(exc), exc, exc.__traceback__)
                return _upstream_error(exc)
            if not upstream.is_success:
                error_body = await upstream.aread()
                await stream_context.__aexit__(None, None, None)
                return Response(
                    content=error_body,
                    status_code=upstream.status_code,
                    headers={"Content-Type": upstream.headers.get("content-type", "application/json")},
                )

            async def upstream_body():
                try:
                    async for chunk in upstream.aiter_bytes():
                        yield chunk
                finally:
                    await stream_context.__aexit__(None, None, None)

            return StreamingResponse(
                upstream_body(),
                status_code=upstream.status_code,
                media_type=upstream.headers.get("content-type", "application/x-ndjson"),
            )

        try:
            response = await request.app.state.ollama_client.post(
                "/api/chat",
                content=body,
                headers={"Content-Type": "application/json"},
            )
        except httpx.HTTPError as exc:
            return _upstream_error(exc)
        return _forward_response(response)

    return app


app = create_app()
