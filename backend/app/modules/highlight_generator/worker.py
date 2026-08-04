from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Callable

from app.config import settings
from app.database import SessionLocal
from app.modules.highlight_generator.models import (
    HighlightCandidate,
    HighlightRecording,
    RenderedHighlight,
)
from app.platform.events import add_outbox_event
from app.platform.models import BackgroundJob, MediaAsset, utcnow


Runner = Callable[..., subprocess.CompletedProcess]
VIDEO_CODECS = {"h264", "hevc", "vp9", "av1"}
AUDIO_CODECS = {"aac", "opus", "vorbis", "mp3", "pcm_s16le", "pcm_s24le"}


def _trusted_path(storage_key: str) -> Path:
    root = Path(settings.highlight_media_dir).resolve()
    path = (root / storage_key).resolve()
    if root not in path.parents:
        raise ValueError("UNSAFE_STORAGE_KEY")
    return path


def _execute(runner: Runner, command: list[str], *, timeout: float) -> subprocess.CompletedProcess:
    result = runner(command, capture_output=True, text=True, timeout=timeout, shell=False)
    if result.returncode != 0:
        detail = str(result.stderr or "media command failed")[-1000:]
        raise RuntimeError(detail)
    return result


def _invalid_recording(recording_id: str, error_code: str, payload: dict | None = None) -> dict:
    db = SessionLocal()
    try:
        recording = db.get(HighlightRecording, recording_id)
        if recording:
            recording.status = "invalid"
            recording.error_code = error_code
            recording.probe_payload = payload
            recording.probed_at = utcnow()
            db.commit()
        return {"recording_id": recording_id, "status": "invalid", "error_code": error_code}
    finally:
        db.close()


def process_probe_job(job_id: str, *, runner: Runner = subprocess.run) -> dict:
    db = SessionLocal()
    try:
        job = db.get(BackgroundJob, job_id)
        if not job or job.module != "highlight_generator" or job.job_type != "highlight.probe":
            raise ValueError("Unsupported highlight probe job")
        recording_id = str(job.input_ref.get("recording_id", ""))
        recording = db.get(HighlightRecording, recording_id)
        if not recording or not recording.storage_key:
            raise ValueError("Highlight recording context is incomplete")
        if recording.status == "ready":
            return {"recording_id": recording.id, "status": "ready"}
        recording.status = "probing"
        storage_key = recording.storage_key
        db.commit()
    finally:
        db.close()

    input_path = _trusted_path(storage_key)
    result = _execute(
        runner,
        [
            settings.ffprobe_binary,
            "-v", "error",
            "-protocol_whitelist", "file,pipe",
            "-show_entries", "format=format_name,duration,size:stream=codec_type,codec_name,width,height",
            "-of", "json",
            str(input_path),
        ],
        timeout=settings.highlight_probe_timeout_seconds,
    )
    try:
        payload = json.loads(result.stdout)
        format_payload = payload["format"]
        streams = payload["streams"]
        duration_ms = round(float(format_payload["duration"]) * 1000)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return _invalid_recording(recording_id, "INVALID_PROBE_OUTPUT")
    format_names = set(str(format_payload.get("format_name", "")).split(","))
    if not format_names.intersection({"mov", "mp4", "matroska", "webm"}):
        return _invalid_recording(recording_id, "UNSUPPORTED_CONTAINER", payload)
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
    if not video or video.get("codec_name") not in VIDEO_CODECS:
        return _invalid_recording(recording_id, "UNSUPPORTED_VIDEO_CODEC", payload)
    if audio and audio.get("codec_name") not in AUDIO_CODECS:
        return _invalid_recording(recording_id, "UNSUPPORTED_AUDIO_CODEC", payload)
    width, height = int(video.get("width") or 0), int(video.get("height") or 0)
    if duration_ms < 1 or duration_ms > 900_000:
        return _invalid_recording(recording_id, "INVALID_DURATION", payload)
    if width < 1 or height < 1 or width > 7680 or height > 4320:
        return _invalid_recording(recording_id, "INVALID_DIMENSIONS", payload)

    db = SessionLocal()
    try:
        recording = db.get(HighlightRecording, recording_id)
        recording.duration_ms = duration_ms
        recording.width = width
        recording.height = height
        recording.video_codec = str(video["codec_name"])
        recording.audio_codec = str(audio["codec_name"]) if audio else None
        recording.has_audio = bool(audio)
        recording.probe_payload = payload
        recording.status = "ready"
        recording.error_code = None
        recording.probed_at = utcnow()
        add_outbox_event(
            db,
            topic="highlight_generator.events",
            aggregate_type="highlight_recording",
            aggregate_id=recording.id,
            event_type="highlight.recording_ready",
            payload={"recording_id": recording.id, "duration_ms": duration_ms},
        )
        db.commit()
        return {"recording_id": recording.id, "status": "ready"}
    finally:
        db.close()


def _output_dimensions(width: int, height: int) -> tuple[int, int]:
    scale = min(1.0, 1920 / width, 1080 / height)
    output_width = max(320, int(width * scale) // 2 * 2)
    output_height = max(320, int(height * scale) // 2 * 2)
    return output_width, output_height


def process_render_job(job_id: str, *, runner: Runner = subprocess.run) -> dict:
    db = SessionLocal()
    try:
        job = db.get(BackgroundJob, job_id)
        if not job or job.module != "highlight_generator" or job.job_type != "highlight.render":
            raise ValueError("Unsupported highlight render job")
        highlight_id = str(job.input_ref.get("highlight_id", ""))
        highlight = db.get(RenderedHighlight, highlight_id)
        candidate = db.get(HighlightCandidate, highlight.candidate_id) if highlight else None
        recording = db.get(HighlightRecording, candidate.recording_id) if candidate else None
        if not highlight or not candidate or not recording or not recording.storage_key:
            raise ValueError("Highlight render context is incomplete")
        if highlight.status == "ready":
            return {"highlight_id": highlight.id, "status": "ready"}
        source_key = recording.storage_key
        start_ms, duration_ms = highlight.start_ms, highlight.duration_ms
        has_audio = bool(recording.has_audio)
        source_width, source_height = recording.width or 1280, recording.height or 720
        owner_id, server_id, session_id = highlight.created_by_id, highlight.server_id, highlight.session_id
        candidate_id = candidate.id
    finally:
        db.close()

    input_path = _trusted_path(source_key)
    video_key = f"derived/{server_id}/{highlight_id}.mp4"
    thumbnail_key = f"thumbnails/{server_id}/{highlight_id}.jpg"
    video_path = _trusted_path(video_key)
    thumbnail_path = _trusted_path(thumbnail_key)
    video_path.parent.mkdir(parents=True, exist_ok=True)
    thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
    part_video = video_path.with_suffix(".part.mp4")
    part_thumbnail = thumbnail_path.with_suffix(".part.jpg")
    width, height = _output_dimensions(source_width, source_height)
    command = [
        settings.ffmpeg_binary, "-nostdin", "-v", "error", "-y",
        "-ss", f"{start_ms / 1000:.3f}", "-i", str(input_path),
        "-t", f"{duration_ms / 1000:.3f}",
        "-map", "0:v:0", "-map", "0:a:0?", "-sn", "-dn",
        "-vf", f"scale={width}:{height}:flags=lanczos,setsar=1",
        "-c:v", "libx264", "-preset", "medium", "-crf", "22", "-pix_fmt", "yuv420p",
    ]
    if has_audio:
        command += ["-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-af", "loudnorm=I=-16:LRA=11:TP=-1.5"]
    else:
        command += ["-an"]
    command += ["-movflags", "+faststart", str(part_video)]
    try:
        _execute(runner, command, timeout=settings.highlight_render_timeout_seconds)
        _execute(
            runner,
            [
                settings.ffmpeg_binary, "-nostdin", "-v", "error", "-y",
                "-ss", f"{duration_ms / 2000:.3f}", "-i", str(part_video),
                "-frames:v", "1", "-vf", "scale=640:-2", "-q:v", "3", str(part_thumbnail),
            ],
            timeout=settings.highlight_probe_timeout_seconds,
        )
        if not part_video.is_file() or part_video.stat().st_size < 1:
            raise RuntimeError("FFmpeg video output is missing")
        if not part_thumbnail.is_file() or part_thumbnail.stat().st_size < 1:
            raise RuntimeError("FFmpeg thumbnail output is missing")
        part_video.replace(video_path)
        part_thumbnail.replace(thumbnail_path)
    except Exception:
        part_video.unlink(missing_ok=True)
        part_thumbnail.unlink(missing_ok=True)
        raise

    def file_digest(path: Path) -> tuple[int, str]:
        digest = hashlib.sha256()
        size = 0
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                size += len(chunk)
                digest.update(chunk)
        return size, digest.hexdigest()

    video_size, video_sha = file_digest(video_path)
    thumbnail_size, thumbnail_sha = file_digest(thumbnail_path)
    db = SessionLocal()
    try:
        highlight = db.get(RenderedHighlight, highlight_id)
        candidate = db.get(HighlightCandidate, candidate_id)
        video_asset = MediaAsset(
            server_id=server_id, owner_id=owner_id, session_id=session_id,
            kind="highlight_video", storage_key=video_key, mime_type="video/mp4",
            size_bytes=video_size, sha256=video_sha,
        )
        thumbnail_asset = MediaAsset(
            server_id=server_id, owner_id=owner_id, session_id=session_id,
            kind="highlight_thumbnail", storage_key=thumbnail_key, mime_type="image/jpeg",
            size_bytes=thumbnail_size, sha256=thumbnail_sha,
        )
        db.add_all([video_asset, thumbnail_asset])
        db.flush()
        highlight.video_asset_id = video_asset.id
        highlight.thumbnail_asset_id = thumbnail_asset.id
        highlight.width = width
        highlight.height = height
        highlight.status = "ready"
        highlight.completed_at = utcnow()
        candidate.status = "rendered"
        add_outbox_event(
            db,
            topic="highlight_generator.events",
            aggregate_type="rendered_highlight",
            aggregate_id=highlight.id,
            event_type="highlight.rendered",
            payload={"highlight_id": highlight.id, "video_asset_id": video_asset.id},
        )
        db.commit()
        return {"highlight_id": highlight.id, "status": "ready"}
    except Exception:
        video_path.unlink(missing_ok=True)
        thumbnail_path.unlink(missing_ok=True)
        raise
    finally:
        db.close()


MEDIA_HANDLERS = {
    ("highlight_generator", "highlight.probe"): process_probe_job,
    ("highlight_generator", "highlight.render"): process_render_job,
}
