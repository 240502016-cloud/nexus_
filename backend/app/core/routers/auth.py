from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.auth import create_access_token
from app.core.models import User
from app.core.rate_limit import RateLimiter
from app.core.security import verify_password
from app.database import get_db

router = APIRouter(prefix="/auth", tags=["auth"])

# IP başına 5 dakikada en fazla 10 giriş denemesi - kaba kuvvet (brute-force) saldırılarını yavaşlatır.
_login_limiter = RateLimiter(max_calls=10, window_seconds=300)


def _enforce_login_rate_limit(request: Request) -> None:
    client_ip = request.client.host if request.client else "unknown"
    if not _login_limiter.allow(client_ip):
        raise HTTPException(status_code=429, detail="Çok fazla giriş denemesi, birkaç dakika sonra tekrar deneyin")


@router.post("/login", dependencies=[Depends(_enforce_login_rate_limit)])
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form.username).first()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Kullanıcı adı veya parola hatalı")
    return {"access_token": create_access_token(user.id), "token_type": "bearer"}
