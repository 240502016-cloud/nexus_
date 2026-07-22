from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core import schemas
from app.core.auth import get_current_user
from app.core.matrix_client import MatrixError, matrix_client
from app.core.models import User
from app.core.security import hash_password
from app.database import get_db

router = APIRouter(prefix="/users", tags=["users"])


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
