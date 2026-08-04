from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.models import User
from app.database import get_db
from app.modules.highlight_generator import schemas
from app.modules.highlight_generator.models import HighlightCandidate, RenderedHighlight
from app.modules.highlight_generator.service import (
    _recording_for_member,
    candidate_to_dict,
    create_marker,
    create_recording,
    queue_render,
    receive_recording_content,
    recording_to_dict,
    rendered_to_dict,
    resolve_asset,
    submit_feedback,
)


router = APIRouter(tags=["highlight-generator"])


@router.post(
    "/servers/{server_id}/highlight/recordings",
    response_model=schemas.RecordingRead,
    status_code=201,
)
def post_recording(
    server_id: int,
    payload: schemas.RecordingCreate,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return recording_to_dict(
        create_recording(
            db,
            server_id=server_id,
            actor=current_user,
            payload=payload,
            idempotency_key=idempotency_key,
        )
    )


@router.put("/highlight/recordings/{recording_id}/content", response_model=schemas.RecordingRead)
async def put_recording_content(
    recording_id: str,
    request: Request,
    content_length: int | None = Header(default=None, alias="Content-Length", ge=1),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    recording = await receive_recording_content(
        db,
        recording_id=recording_id,
        actor=current_user,
        stream=request.stream(),
        content_length=content_length,
    )
    return recording_to_dict(recording)


@router.get("/highlight/recordings/{recording_id}", response_model=schemas.RecordingRead)
def get_recording(
    recording_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return recording_to_dict(_recording_for_member(db, recording_id, current_user))


@router.post(
    "/highlight/recordings/{recording_id}/markers",
    response_model=schemas.CandidateRead,
    status_code=201,
)
def post_marker(
    recording_id: str,
    payload: schemas.MarkerCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return candidate_to_dict(
        create_marker(db, recording_id=recording_id, actor=current_user, payload=payload)
    )


@router.get(
    "/highlight/recordings/{recording_id}/candidates",
    response_model=list[schemas.CandidateRead],
)
def list_candidates(
    recording_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    recording = _recording_for_member(db, recording_id, current_user)
    rows = (
        db.query(HighlightCandidate)
        .filter(HighlightCandidate.recording_id == recording.id)
        .order_by(HighlightCandidate.score.desc(), HighlightCandidate.created_at)
        .all()
    )
    return [candidate_to_dict(row) for row in rows]


@router.post(
    "/highlight/candidates/{candidate_id}/render",
    response_model=schemas.RenderedHighlightRead,
    status_code=202,
)
def post_highlight_render(
    candidate_id: str,
    payload: schemas.RenderHighlightCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    highlight = queue_render(db, candidate_id=candidate_id, actor=current_user, payload=payload)
    return rendered_to_dict(db, highlight)


@router.get("/highlight/renders/{highlight_id}", response_model=schemas.RenderedHighlightRead)
def get_highlight_render(
    highlight_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    highlight = db.get(RenderedHighlight, highlight_id)
    if not highlight:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Highlight bulunamadı")
    _recording_for_member(
        db,
        db.get(HighlightCandidate, highlight.candidate_id).recording_id,
        current_user,
    )
    return rendered_to_dict(db, highlight)


@router.get("/highlight/assets/{asset_id}")
def get_highlight_asset(
    asset_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    asset, path = resolve_asset(db, asset_id=asset_id, actor=current_user)
    return FileResponse(path, media_type=asset.mime_type)


@router.post("/highlight/renders/{highlight_id}/feedback")
def post_highlight_feedback(
    highlight_id: str,
    payload: schemas.HighlightFeedbackCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = submit_feedback(db, highlight_id=highlight_id, actor=current_user, payload=payload)
    return {"id": row.id, "feedback_type": row.feedback_type, "updated_at": row.updated_at}

