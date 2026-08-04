from fastapi import APIRouter, Depends, Header, Response
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.models import User
from app.database import get_db
from app.modules.meme_generator import schemas
from app.modules.meme_generator.service import (
    create_generation,
    delete_meme,
    generated_meme_to_dict,
    generation_to_accepted,
    get_candidates,
    list_templates,
    render_generation,
    resolve_asset,
    submit_feedback,
    update_preference,
)


router = APIRouter(tags=["meme-generator"])


@router.get("/servers/{server_id}/memes/templates", response_model=list[schemas.MemeTemplateRead])
def get_meme_templates(
    server_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Membership is checked through preferences only when needed; a harmless catalog
    # still requires an authenticated server member via this no-op preference lookup route.
    from app.modules.meme_generator.service import _server_for_member

    _server_for_member(db, server_id, current_user)
    return list_templates()


@router.post(
    "/servers/{server_id}/memes/jobs",
    response_model=schemas.MemeJobAccepted,
    status_code=202,
)
def post_meme_job(
    server_id: int,
    payload: schemas.MemeGenerationCreate,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    generation = create_generation(
        db,
        server_id=server_id,
        actor=current_user,
        payload=payload,
        idempotency_key=idempotency_key,
    )
    return generation_to_accepted(generation)


@router.get("/memes/jobs/{job_id}/candidates", response_model=schemas.MemeCandidateResponse)
def get_meme_candidates(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_candidates(db, generation_id=job_id, actor=current_user)


@router.post("/memes/jobs/{job_id}/render", response_model=schemas.GeneratedMemeRead)
def post_render_meme(
    job_id: str,
    payload: schemas.RenderMemeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    meme = render_generation(db, generation_id=job_id, actor=current_user, payload=payload)
    return generated_meme_to_dict(db, meme)


@router.get("/memes/assets/{asset_id}")
def get_meme_asset(
    asset_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    asset, path = resolve_asset(db, asset_id=asset_id, actor=current_user)
    return FileResponse(path, media_type=asset.mime_type, filename=f"nexus-meme-{asset.id}.png")


@router.post("/memes/{meme_id}/feedback", response_model=schemas.MemeFeedbackRead)
def post_meme_feedback(
    meme_id: str,
    payload: schemas.MemeFeedbackCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return submit_feedback(db, meme_id=meme_id, actor=current_user, payload=payload)


@router.delete("/memes/{meme_id}", status_code=204)
def remove_meme(
    meme_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    delete_meme(db, meme_id=meme_id, actor=current_user)
    return Response(status_code=204)


@router.put(
    "/servers/{server_id}/memes/preferences/me",
    response_model=schemas.MemePreferenceRead,
)
def put_meme_preference(
    server_id: int,
    payload: schemas.MemePreferenceUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return update_preference(db, server_id=server_id, actor=current_user, payload=payload)

