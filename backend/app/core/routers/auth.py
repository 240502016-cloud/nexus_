from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.auth import create_access_token
from app.core.models import User
from app.core.rate_limit import RateLimiter
from app.core.security import verify_password
from app.database import get_db

router = APIRouter(prefix="/auth", tags=["auth"])

# Kullanıcı adı + istemci adresi başına sınır koy. Aynı ev/okul ağı veya reverse proxy
# arkasındaki farklı kullanıcılar birbirinin giriş hakkını tüketmemeli.
_login_limiter = RateLimiter(max_calls=10, window_seconds=300)


def _enforce_login_rate_limit(request: Request, username: str) -> None:
    client_ip = request.client.host if request.client else "unknown"
    if not _login_limiter.allow(f"{client_ip}:{username.strip().casefold()}"):
        raise HTTPException(status_code=429, detail="Çok fazla giriş denemesi, birkaç dakika sonra tekrar deneyin")


@router.post("/login")
def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    _enforce_login_rate_limit(request, form.username)
    user = db.query(User).filter(User.username == form.username).first()
    if not user or not user.is_active or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Kullanıcı adı veya parola hatalı")
    return {
        "access_token": create_access_token(user.id, user.auth_version),
        "token_type": "bearer",
    }
