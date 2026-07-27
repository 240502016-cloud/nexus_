from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.config import settings
from app.core import schemas
from app.core.auth import get_current_user
from app.core.models import User

router = APIRouter(prefix="/attachments", tags=["attachments"])

_ID = re.compile(r"^[0-9a-f]{32}$")
_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}


def _storage() -> Path:
    path = Path(settings.attachment_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_name(name: str | None) -> str:
    cleaned = Path(name or "dosya").name.replace("\x00", "").strip()
    return cleaned[:180] or "dosya"


@router.post("", response_model=schemas.AttachmentRead, status_code=201)
async def upload_attachment(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    attachment_id = uuid.uuid4().hex
    data_path = _storage() / f"{attachment_id}.data"
    metadata_path = _storage() / f"{attachment_id}.json"
    size = 0
    try:
        with data_path.open("wb") as target:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > settings.attachment_max_bytes:
                    raise HTTPException(status_code=413, detail="Dosya en fazla 25 MB olabilir")
                target.write(chunk)
        content_type = (file.content_type or "application/octet-stream").lower()
        is_image = content_type in _IMAGE_TYPES
        metadata = {
            "id": attachment_id,
            "name": _safe_name(file.filename),
            "size": size,
            "content_type": content_type if is_image else "application/octet-stream",
            "is_image": is_image,
            "owner_id": current_user.id,
        }
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
    except Exception:
        data_path.unlink(missing_ok=True)
        metadata_path.unlink(missing_ok=True)
        raise
    return schemas.AttachmentRead(**metadata, url=f"/api/attachments/{attachment_id}")


@router.get("/{attachment_id}")
def download_attachment(attachment_id: str):
    if not _ID.fullmatch(attachment_id):
        raise HTTPException(status_code=404, detail="Dosya bulunamadı")
    data_path = _storage() / f"{attachment_id}.data"
    metadata_path = _storage() / f"{attachment_id}.json"
    if not data_path.is_file() or not metadata_path.is_file():
        raise HTTPException(status_code=404, detail="Dosya bulunamadı")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    disposition = "inline" if metadata.get("is_image") else "attachment"
    return FileResponse(
        data_path,
        media_type=metadata.get("content_type", "application/octet-stream"),
        filename=metadata.get("name", "dosya"),
        content_disposition_type=disposition,
        headers={
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, max-age=86400",
        },
    )
