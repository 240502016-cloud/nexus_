from __future__ import annotations

import asyncio
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.core.models import Server, ServerMember, User
from app.database import Base
from app.modules.highlight_generator.models import (
    HighlightCandidate,
    HighlightRecording,
    RenderedHighlight,
)
from app.modules.highlight_generator.metadata_worker import process_highlight_metadata_job
from app.modules.highlight_generator.schemas import MarkerCreate, RecordingCreate, RenderHighlightCreate
from app.modules.highlight_generator.service import (
    create_marker,
    create_recording,
    queue_render,
    receive_recording_content,
    resolve_asset,
)
from app.modules.highlight_generator.worker import process_probe_job, process_render_job
from app.platform.models import BackgroundJob, MediaAsset
from app.platform.worker import process_one as process_platform_one


class HighlightGeneratorTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.owner = User(username="highlight-owner", email="highlight-owner@test", hashed_password="x")
        self.friend = User(username="highlight-friend", email="highlight-friend@test", hashed_password="x")
        self.third = User(username="highlight-third", email="highlight-third@test", hashed_password="x")
        self.outsider = User(username="highlight-out", email="highlight-out@test", hashed_password="x")
        self.db.add_all([self.owner, self.friend, self.third, self.outsider])
        self.db.flush()
        self.server = Server(name="Highlight Server", owner_id=self.owner.id)
        self.db.add(self.server)
        self.db.flush()
        self.db.add_all(
            [
                ServerMember(user_id=self.owner.id, server_id=self.server.id),
                ServerMember(user_id=self.friend.id, server_id=self.server.id),
                ServerMember(user_id=self.third.id, server_id=self.server.id),
            ]
        )
        self.db.commit()
        self.media_dir = tempfile.TemporaryDirectory()
        self.media_patch = patch.object(settings, "highlight_media_dir", self.media_dir.name)
        self.media_patch.start()
        self.video = b"synthetic-video-bytes-for-worker-contract"

    def tearDown(self):
        self.media_patch.stop()
        self.media_dir.cleanup()
        self.db.close()
        self.engine.dispose()

    def create(self) -> HighlightRecording:
        return create_recording(
            self.db,
            server_id=self.server.id,
            actor=self.owner,
            payload=RecordingCreate(
                source_type="OBS_REPLAY_BUFFER",
                original_filename="replay.mkv",
                byte_size=len(self.video),
                content_type="video/x-matroska",
            ),
            idempotency_key="highlight-recording-001",
        )

    async def _stream(self, data: bytes):
        midpoint = len(data) // 2
        yield data[:midpoint]
        yield data[midpoint:]

    def upload(self, recording: HighlightRecording) -> HighlightRecording:
        return asyncio.run(
            receive_recording_content(
                self.db,
                recording_id=recording.id,
                actor=self.owner,
                stream=self._stream(self.video),
                content_length=len(self.video),
            )
        )

    @staticmethod
    def fake_probe(command, **kwargs):
        assert kwargs["shell"] is False
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                {
                    "format": {"format_name": "matroska,webm", "duration": "60.0", "size": "42"},
                    "streams": [
                        {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080},
                        {"codec_type": "audio", "codec_name": "aac"},
                    ],
                }
            ),
            stderr="",
        )

    @staticmethod
    def fake_ffmpeg(command, **kwargs):
        assert kwargs["shell"] is False
        output = Path(command[-1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"fake-output:" + output.suffix.encode())
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    def run_probe(self):
        handler = lambda job_id: process_probe_job(job_id, runner=self.fake_probe)
        with patch("app.platform.worker.SessionLocal", self.Session), patch(
            "app.modules.highlight_generator.worker.SessionLocal", self.Session
        ):
            return process_platform_one(handlers={("highlight_generator", "highlight.probe"): handler})

    def test_upload_is_streamed_idempotent_and_ai_worker_does_not_claim_media_job(self):
        recording = self.create()
        self.assertEqual(recording.id, self.create().id)
        recording = self.upload(recording)
        self.assertEqual(recording.status, "uploaded")
        self.assertEqual(self.db.query(MediaAsset).one().size_bytes, len(self.video))
        with patch("app.platform.worker.SessionLocal", self.Session):
            self.assertFalse(process_platform_one())
        self.assertEqual(self.db.query(BackgroundJob).one().status, "queued")

    def test_probe_validates_metadata_and_manual_marker_is_clamped(self):
        recording = self.upload(self.create())
        self.assertTrue(self.run_probe())
        self.db.expire_all()
        recording = self.db.get(HighlightRecording, recording.id)
        self.assertEqual(recording.status, "ready")
        self.assertEqual(recording.duration_ms, 60_000)
        candidate = create_marker(
            self.db,
            recording_id=recording.id,
            actor=self.owner,
            payload=MarkerCreate(
                schema_version="1.0",
                marker_id="highlight-marker-001",
                offset_ms=5_000,
                category_hint="COMEDY",
                participant_player_ids=[self.owner.id, self.friend.id, self.third.id],
                summary="Üç oyuncu aynı anda yanlış kapıyı seçti.",
            ),
        )
        self.assertEqual(candidate.start_ms, 0)
        self.assertEqual(candidate.end_ms, 13_000)
        self.assertEqual(candidate.score, 0.45)
        self.assertTrue(candidate.meme_candidate)

    def test_render_uses_trusted_argument_array_and_private_assets(self):
        recording = self.upload(self.create())
        self.run_probe()
        self.db.expire_all()
        candidate = create_marker(
            self.db,
            recording_id=recording.id,
            actor=self.owner,
            payload=MarkerCreate(
                schema_version="1.0",
                marker_id="highlight-marker-render",
                offset_ms=30_000,
                category_hint="SKILL",
                participant_player_ids=[self.owner.id],
                summary="Owner son anda raundu çevirdi.",
            ),
        )
        highlight = queue_render(
            self.db,
            candidate_id=candidate.id,
            actor=self.owner,
            payload=RenderHighlightCreate(title_override="Son saniye dönüşü"),
        )
        handler = lambda job_id: process_render_job(job_id, runner=self.fake_ffmpeg)
        with patch("app.platform.worker.SessionLocal", self.Session), patch(
            "app.modules.highlight_generator.worker.SessionLocal", self.Session
        ):
            self.assertTrue(
                process_platform_one(handlers={("highlight_generator", "highlight.render"): handler})
            )
        self.db.expire_all()
        highlight = self.db.get(RenderedHighlight, highlight.id)
        self.assertEqual(highlight.status, "ready")
        self.assertEqual(self.db.get(HighlightCandidate, candidate.id).status, "rendered")
        self.assertEqual(self.db.query(MediaAsset).count(), 3)
        video_asset, path = resolve_asset(self.db, asset_id=highlight.video_asset_id, actor=self.friend)
        self.assertTrue(path.is_file())
        self.assertEqual(video_asset.mime_type, "video/mp4")
        with self.assertRaises(HTTPException) as forbidden:
            resolve_asset(self.db, asset_id=highlight.video_asset_id, actor=self.outsider)
        self.assertEqual(forbidden.exception.status_code, 403)

    def test_verified_marker_metadata_uses_ai_gateway_without_video_bytes(self):
        recording = self.upload(self.create())
        self.run_probe()
        self.db.expire_all()
        candidate = create_marker(
            self.db,
            recording_id=recording.id,
            actor=self.owner,
            payload=MarkerCreate(
                schema_version="1.0",
                marker_id="highlight-marker-metadata",
                offset_ms=30_000,
                category_hint="SKILL",
                participant_player_ids=[self.owner.id],
                summary="Owner son saniyede raundu çevirdi.",
            ),
        )

        def fake_chat(_model, messages, **_kwargs):
            prompt = messages[-1]["content"]
            self.assertIn("Owner son saniyede raundu çevirdi", prompt)
            self.assertNotIn("synthetic-video-bytes", prompt)
            return {
                "model": "test-highlight-model",
                "message": {
                    "content": json.dumps(
                        {
                            "title": "Son Saniye Dönüşü",
                            "description": "Raund son anda geri alındı.",
                            "memeCandidate": False,
                            "loreCandidate": False,
                        },
                        ensure_ascii=False,
                    )
                },
            }

        handler = lambda job_id: process_highlight_metadata_job(job_id, chat=fake_chat)
        with patch("app.platform.worker.SessionLocal", self.Session), patch(
            "app.modules.highlight_generator.metadata_worker.SessionLocal", self.Session
        ):
            self.assertTrue(
                process_platform_one(handlers={("highlight_generator", "highlight.metadata"): handler})
            )
        self.db.expire_all()
        candidate = self.db.get(HighlightCandidate, candidate.id)
        self.assertEqual(candidate.title, "Son Saniye Dönüşü")
        self.assertEqual(candidate.description, "Raund son anda geri alındı.")

    def test_invalid_size_and_out_of_bounds_marker_fail_closed(self):
        recording = self.create()
        with self.assertRaises(HTTPException) as mismatch:
            asyncio.run(
                receive_recording_content(
                    self.db,
                    recording_id=recording.id,
                    actor=self.owner,
                    stream=self._stream(self.video[:-1]),
                    content_length=len(self.video) - 1,
                )
            )
        self.assertEqual(mismatch.exception.status_code, 422)
        self.assertFalse(any(Path(self.media_dir.name).rglob("*.part")))


if __name__ == "__main__":
    unittest.main()
