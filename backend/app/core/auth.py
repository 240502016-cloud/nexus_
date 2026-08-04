from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.config import settings
from app.core.models import User
from app.database import get_db

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 gün

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def create_access_token(user_id: int, auth_version: int = 0) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "ver": auth_version, "exp": expire}
    return jwt.encode(payload, settings.core_api_secret_key, algorithm=ALGORITHM)


def decode_user_claims(token: str) -> tuple[int, int] | None:
    """JWT'den kullanıcı ve oturum sürümünü çıkarır; eski token'lar sürüm 0 kabul edilir."""
    try:
        payload = jwt.decode(token, settings.core_api_secret_key, algorithms=[ALGORITHM])
        user_id = int(payload["sub"])
        auth_version = int(payload.get("ver", 0))
        if user_id <= 0 or auth_version < 0:
            return None
        return user_id, auth_version
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


def decode_user_id(token: str) -> int | None:
    """HTTP dışı eski çağrılar için kullanıcı kimliğini döndüren uyumluluk yardımcısı."""
    claims = decode_user_claims(token)
    return claims[0] if claims else None


def claims_match_user(claims: tuple[int, int] | None, user: User | None) -> bool:
    return bool(
        claims
        and user
        and user.is_active
        and claims[0] == user.id
        and claims[1] == user.auth_version
    )


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_error = HTTPException(status_code=401, detail="Kimlik doğrulanamadı")
    claims = decode_user_claims(token)
    if claims is None:
        raise credentials_error

    user = db.get(User, claims[0])
    if not claims_match_user(claims, user):
        raise credentials_error
    return user
