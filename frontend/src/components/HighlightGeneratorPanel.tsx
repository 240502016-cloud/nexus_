import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";

import { ApiError, coreApi } from "../api/client";
import type {
  HighlightCandidate,
  HighlightRecording,
  Member,
  RenderedHighlight,
  Server,
  User,
} from "../types";
import { Icon } from "./Icon";


function localId(): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  return `highlight-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}


export function HighlightGeneratorPanel({
  server,
  members,
  currentUser,
  onClose,
}: {
  server: Server;
  members: Member[];
  currentUser: User;
  onClose: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [recording, setRecording] = useState<HighlightRecording | null>(null);
  const [candidate, setCandidate] = useState<HighlightCandidate | null>(null);
  const [highlight, setHighlight] = useState<RenderedHighlight | null>(null);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [category, setCategory] = useState<"SKILL" | "COMEDY" | "FAILURE" | "CHAOS" | "LORE_WORTHY">("COMEDY");
  const [summary, setSummary] = useState("");
  const [offsetSeconds, setOffsetSeconds] = useState(0);
  const [startSeconds, setStartSeconds] = useState(0);
  const [endSeconds, setEndSeconds] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const requestKey = useRef(localId());

  useEffect(() => () => {
    if (videoUrl) URL.revokeObjectURL(videoUrl);
  }, [videoUrl]);

  useEffect(() => {
    if (!recording || !["UPLOADED", "PROBING"].includes(recording.status)) return;
    const timer = window.setInterval(() => {
      void coreApi.getHighlightRecording(recording.id).then((next) => {
        setRecording(next);
        if (next.status === "READY" && next.duration_ms) {
          setOffsetSeconds(Math.max(1, Math.floor(next.duration_ms / 1000) - 5));
        }
      }).catch(() => undefined);
    }, 1_500);
    return () => window.clearInterval(timer);
  }, [recording?.id, recording?.status]);

  useEffect(() => {
    if (!highlight || !["QUEUED", "RENDERING"].includes(highlight.status)) return;
    const timer = window.setInterval(() => {
      void coreApi.getRenderedHighlight(highlight.id).then(async (next) => {
        setHighlight(next);
        if (next.status === "READY" && next.video_url) {
          const blob = await coreApi.getHighlightAsset(next.video_url);
          setVideoUrl(URL.createObjectURL(blob));
        }
      }).catch(() => undefined);
    }, 1_500);
    return () => window.clearInterval(timer);
  }, [highlight?.id, highlight?.status]);

  async function upload(event: FormEvent) {
    event.preventDefault();
    if (!file) return;
    const extension = file.name.toLowerCase().endsWith(".mkv") ? "video/x-matroska" : "video/mp4";
    setBusy(true);
    setError(null);
    try {
      const created = await coreApi.createHighlightRecording(
        server.id,
        {
          source_type: "OBS_REPLAY_BUFFER",
          original_filename: file.name,
          byte_size: file.size,
          content_type: extension,
        },
        requestKey.current,
      );
      const uploaded = created.upload_url
        ? await coreApi.uploadHighlightContent(created.upload_url, file)
        : created;
      setRecording(uploaded);
      setNotice("Video özel alana yüklendi; FFprobe doğrulaması bekleniyor.");
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Video yüklenemedi.");
    } finally {
      setBusy(false);
    }
  }

  async function mark(event: FormEvent) {
    event.preventDefault();
    if (!recording?.duration_ms || !summary.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const next = await coreApi.createHighlightMarker(recording.id, {
        schema_version: "1.0",
        marker_id: localId(),
        source: "MANUAL",
        offset_ms: Math.round(offsetSeconds * 1000),
        category_hint: category,
        participant_player_ids: [currentUser.id],
        summary: summary.trim(),
        manual_priority: 1,
      });
      setCandidate(next);
      setStartSeconds(next.start_ms / 1000);
      setEndSeconds(next.end_ms / 1000);
      setNotice("Marker doğrulandı. Render öncesi trim aralığını kontrol edin.");
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Marker oluşturulamadı.");
    } finally {
      setBusy(false);
    }
  }

  async function render() {
    if (!candidate) return;
    setBusy(true);
    setError(null);
    try {
      const next = await coreApi.renderHighlight(candidate.id, {
        start_ms: Math.round(startSeconds * 1000),
        end_ms: Math.round(endSeconds * 1000),
        title_override: candidate.title,
        variant: "LANDSCAPE",
      });
      setHighlight(next);
      setNotice("Highlight ağsız medya işçisine gönderildi.");
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Render başlatılamadı.");
    } finally {
      setBusy(false);
    }
  }

  function reset() {
    setFile(null);
    setRecording(null);
    setCandidate(null);
    setHighlight(null);
    setVideoUrl(null);
    setSummary("");
    setNotice(null);
    requestKey.current = localId();
  }

  const durationSeconds = (recording?.duration_ms ?? 0) / 1000;
  return (
    <div className="settings-overlay" onClick={onClose}>
      <section className="settings-panel settings-panel--wide highlight-panel" onClick={(event) => event.stopPropagation()} aria-label="Highlight Generator">
        <header className="settings-panel__header">
          <div><span className="panel-eyebrow">ÖZEL OBS REPLAY AKIŞI</span><h2>Highlight Generator</h2></div>
          <button className="settings-panel__close" onClick={onClose} aria-label="Kapat"><Icon name="close" /></button>
        </header>
        {error ? <div className="commentator-panel__message is-error">{error}</div> : null}
        {notice ? <div className="commentator-panel__message">{notice}</div> : null}

        {!recording ? (
          <form className="highlight-panel__upload" onSubmit={upload}>
            <label>
              <span>OBS Replay Buffer dosyası</span>
              <input type="file" accept="video/mp4,.mkv,video/x-matroska" onChange={(event) => setFile(event.target.files?.[0] ?? null)} required />
            </label>
            <p>MP4/MKV · en fazla 1 GiB ve 15 dakika · Nexus ekranınızı sürekli kaydetmez.</p>
            <button type="submit" disabled={busy || !file}>{busy ? "Yükleniyor…" : "Özel kaydı yükle"}</button>
          </form>
        ) : null}

        {recording ? (
          <section className="highlight-panel__recording">
            <header>
              <div><span>DOSYA</span><strong>{recording.original_filename}</strong></div>
              <div><span>DURUM</span><strong>{recording.status}</strong></div>
              {recording.duration_ms ? <div><span>SÜRE</span><strong>{durationSeconds.toFixed(1)} sn</strong></div> : null}
              <button type="button" onClick={reset}>Yeni kayıt</button>
            </header>
            {recording.status === "INVALID" ? <div className="commentator-panel__empty">Dosya reddedildi: {recording.error_code}</div> : null}
            {["UPLOADED", "PROBING"].includes(recording.status) ? <div className="commentator-panel__empty">Codec, süre ve stream bilgileri doğrulanıyor…</div> : null}
          </section>
        ) : null}

        {recording?.status === "READY" && !candidate ? (
          <form className="highlight-panel__marker" onSubmit={mark}>
            <label><span>Kategori</span><select value={category} onChange={(event) => setCategory(event.target.value as typeof category)}><option value="SKILL">Beceri</option><option value="COMEDY">Komedi</option><option value="FAILURE">Başarısızlık</option><option value="CHAOS">Kaos</option><option value="LORE_WORTHY">Lore adayı</option></select></label>
            <label><span>Olay saniyesi</span><input type="number" min="0" max={durationSeconds} step="0.1" value={offsetSeconds} onChange={(event) => setOffsetSeconds(Number(event.target.value))} /></label>
            <label className="highlight-panel__wide"><span>Olgusal kısa açıklama</span><textarea maxLength={500} value={summary} onChange={(event) => setSummary(event.target.value)} required /></label>
            <small className="highlight-panel__wide">Katılımcı: {members.find((member) => member.id === currentUser.id)?.display_name || currentUser.display_name || currentUser.username}</small>
            <button className="highlight-panel__wide" disabled={busy || !summary.trim()}>Aday aralığı oluştur</button>
          </form>
        ) : null}

        {candidate ? (
          <section className="highlight-panel__trim">
            <header><div><span>{candidate.primary_category} · %{Math.round(candidate.score * 100)}</span><strong>{candidate.title}</strong></div></header>
            <div><label><span>Başlangıç (sn)</span><input type="number" min="0" max={endSeconds - 1} step="0.1" value={startSeconds} onChange={(event) => setStartSeconds(Number(event.target.value))} /></label><label><span>Bitiş (sn)</span><input type="number" min={startSeconds + 1} max={durationSeconds} step="0.1" value={endSeconds} onChange={(event) => setEndSeconds(Number(event.target.value))} /></label></div>
            {!highlight ? <button type="button" disabled={busy} onClick={() => void render()}>{busy ? "Sıraya alınıyor…" : "MP4 highlight render et"}</button> : null}
          </section>
        ) : null}

        {highlight ? <div className="highlight-panel__status"><strong>{highlight.status}</strong><span>{(highlight.duration_ms / 1000).toFixed(1)} sn · {highlight.error_code || "H.264/AAC private artifact"}</span></div> : null}
        {videoUrl ? <video className="highlight-panel__video" src={videoUrl} controls preload="metadata" /> : null}
      </section>
    </div>
  );
}

