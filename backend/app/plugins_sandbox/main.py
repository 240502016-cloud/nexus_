from __future__ import annotations

import hmac
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field


PLUGIN_ROOT = Path(os.getenv("PLUGIN_ROOT", "/srv/plugins")).resolve()
BACKEND_ROOT = Path(__file__).resolve().parents[2]
SANDBOX_KEY = os.getenv("PLUGIN_SANDBOX_API_KEY", "")
TIMEOUT_SECONDS = float(os.getenv("PLUGIN_SANDBOX_TIMEOUT_SECONDS", "10"))
MAX_OUTPUT_BYTES = int(os.getenv("PLUGIN_SANDBOX_MAX_OUTPUT_BYTES", "65536"))
MAX_PAYLOAD_BYTES = int(os.getenv("PLUGIN_SANDBOX_MAX_PAYLOAD_BYTES", "65536"))
_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")
_ENTRY_POINT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*:[A-Za-z_][A-Za-z0-9_]*$")


class ExecuteRequest(BaseModel):
    entry_point: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*:[A-Za-z_][A-Za-z0-9_]*$")
    context: dict


app = FastAPI(title="Nexus Plugin Sandbox", docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/execute/{plugin_name}")
def execute(
    plugin_name: str,
    payload: ExecuteRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    if not SANDBOX_KEY or not authorization or not hmac.compare_digest(
        authorization, f"Bearer {SANDBOX_KEY}"
    ):
        raise HTTPException(status_code=401, detail="Geçersiz sandbox kimliği")
    if not _NAME_RE.fullmatch(plugin_name):
        raise HTTPException(status_code=400, detail="Geçersiz plugin adı")
    if not _ENTRY_POINT_RE.fullmatch(payload.entry_point):
        raise HTTPException(status_code=400, detail="Geçersiz plugin entry point")
    if len(payload.model_dump_json().encode("utf-8")) > MAX_PAYLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Plugin sandbox isteği çok büyük")

    plugin_dir = (PLUGIN_ROOT / plugin_name).resolve()
    if plugin_dir.parent != PLUGIN_ROOT or not plugin_dir.is_dir():
        raise HTTPException(status_code=404, detail="Plugin sandbox içinde bulunamadı")
    module_name, _, function_name = payload.entry_point.partition(":")
    module_path = (plugin_dir / f"{module_name}.py").resolve()
    if module_path.parent != plugin_dir or not module_path.is_file():
        raise HTTPException(status_code=422, detail="Plugin modülü bulunamadı")

    try:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "app.plugins_sandbox.runner",
                str(module_path),
                function_name,
            ],
            input=json.dumps(payload.context, ensure_ascii=False),
            text=True,
            capture_output=True,
            cwd=str(plugin_dir),
            timeout=max(0.1, TIMEOUT_SECONDS),
            check=False,
            env={
                **{key: value for key, value in os.environ.items() if key != "PLUGIN_SANDBOX_API_KEY"},
                "PYTHONPATH": str(BACKEND_ROOT),
            },
        )
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail="Plugin sandbox zaman aşımına uğradı") from exc

    if completed.returncode != 0:
        raise HTTPException(status_code=422, detail="Plugin sandbox çalıştırma hatası")
    if len(completed.stdout.encode("utf-8")) > MAX_OUTPUT_BYTES:
        raise HTTPException(status_code=413, detail="Plugin sandbox çıktısı çok büyük")
    try:
        result = json.loads(completed.stdout)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Plugin sandbox geçersiz çıktı üretti") from exc
    if not isinstance(result, dict) or "output" not in result:
        raise HTTPException(status_code=422, detail="Plugin sandbox yanıtı geçersiz")
    return {"output": str(result["output"])}
