import os
import re
import secrets

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core import schemas
from app.core.auth import get_current_user
from app.core.matrix_client import MatrixError, matrix_client
from app.core.models import User
from app.core.rate_limit import RateLimiter
from app.core.security import hash_password, verify_password
from app.database import get_db

router = APIRouter(prefix="/users", tags=["users"])

# ---- Profil fotoğrafı (avatar) depolama ----
AVATAR_DIR = os.environ.get("AVATAR_DIR", "/srv/avatars")
os.makedirs(AVATAR_DIR, exist_ok=True)
MAX_AVATAR_BYTES = 2 * 1024 * 1024  # 2 MB
AVATAR_URL_PREFIX = "/api/users/avatars/"
_SAFE_AVATAR_NAME = re.compile(r"^[A-Za-z0-9_]+\.(png|jpg|jpeg|webp|gif)$")
# Aynı kullanıcıdan kısa sürede çok fazla yükleme engellenir.
_avatar_limiter = RateLimiter(max_calls=5, window_seconds=60)


def _detect_image_ext(data: bytes) -> str | None:
    """Uzantıya DEĞİL, dosyanın sihirli baytlarına bakarak görsel türünü belirler."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def _delete_avatar_file(avatar_url: str | None) -> None:
    """Bir kullanıcının eski avatar dosyasını (bizim dizinimizdeyse) güvenle siler."""
    if not avatar_url or not avatar_url.startswith(AVATAR_URL_PREFIX):
        return
    name = avatar_url[len(AVATAR_URL_PREFIX) :]
    if not _SAFE_AVATAR_NAME.match(name):
        return
    path = os.path.join(AVATAR_DIR, name)
    try:
        if os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass  # best-effort temizlik


@router.post("", response_model=schemas.UserRead, status_code=201)
def create_user(payload: schemas.UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status_code=409, detail="Bu kullanıcı adı zaten alınmış")

    try:
        matrix_account = matrix_client.register_user(payload.username, payload.password)
    except MatrixError as exc:
        raise HTTPException(status_code=502, detail=f"Matrix hesabı oluşturulamadı: {exc}") from exc

    user = User(
        username=payload.username,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        display_name=payload.display_name,
        avatar_url=payload.avatar_url,
        matrix_user_id=matrix_account["user_id"],
        matrix_access_token=matrix_account["access_token"],
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/me", response_model=schemas.UserRead)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/me", response_model=schemas.UserRead)
def update_me(
    payload: schemas.UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Kullanıcının kendi profilini günceller (şu an: görünen ad)."""
    user = db.get(User, current_user.id)
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    # UserUpdate yalnızca display_name içerir; boş/null gönderilirse görünen ad temizlenir.
    user.display_name = (payload.display_name or "").strip() or None
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/me/password", status_code=204)
def change_password(
    payload: schemas.PasswordChange,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mevcut parolayı doğrulayıp yeni parolayı ayarlar."""
    user = db.get(User, current_user.id)
    if not user or not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(status_code=403, detail="Mevcut parola yanlış")
    user.hashed_password = hash_password(payload.new_password)
    db.add(user)
    db.commit()


@router.post("/me/avatar", response_model=schemas.UserRead)
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Profil fotoğrafı yükler: kimlik doğrulama + boyut/MIME (sihirli bayt) doğrulama + rate limit."""
    if not _avatar_limiter.allow(str(current_user.id)):
        raise HTTPException(status_code=429, detail="Çok fazla yükleme; biraz sonra tekrar deneyin")

    data = await file.read(MAX_AVATAR_BYTES + 1)
    if len(data) > MAX_AVATAR_BYTES:
        raise HTTPException(status_code=413, detail="Dosya çok büyük (en fazla 2 MB)")
    if not data:
        raise HTTPException(status_code=400, detail="Boş dosya")

    ext = _detect_image_ext(data)
    if ext is None:
        raise HTTPException(status_code=415, detail="Desteklenmeyen veya geçersiz görsel (PNG/JPEG/WEBP/GIF)")

    user = db.get(User, current_user.id)
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")

    filename = f"{user.id}_{secrets.token_hex(8)}.{ext}"
    with open(os.path.join(AVATAR_DIR, filename), "wb") as fh:
        fh.write(data)

    _delete_avatar_file(user.avatar_url)  # eski avatarı temizle
    user.avatar_url = f"{AVATAR_URL_PREFIX}{filename}"
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/avatars/{filename}")
def get_avatar(filename: str):
    """Yüklenmiş avatarı sunar. Filename sıkı doğrulanır (path traversal engellenir)."""
    if not _SAFE_AVATAR_NAME.match(filename):
        raise HTTPException(status_code=404, detail="Bulunamadı")
    path = os.path.join(AVATAR_DIR, filename)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Bulunamadı")
    return FileResponse(path, headers={"Cache-Control": "public, max-age=86400"})


@router.get("/{user_id}", response_model=schemas.UserRead)
def get_user(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    return user
