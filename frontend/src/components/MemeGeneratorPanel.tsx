import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";

import { ApiError, coreApi } from "../api/client";
import type {
  GeneratedMeme,
  Member,
  MemeCandidateResponse,
  MemeMomentType,
  Server,
  User,
} from "../types";
import { Icon } from "./Icon";


const MOMENTS: Array<{ value: MemeMomentType; label: string }> = [
  { value: "FAILURE", label: "Komik başarısızlık" },
  { value: "SUCCESS", label: "Beklenmedik başarı" },
  { value: "PREPARATION", label: "Boşa giden hazırlık" },
  { value: "NAVIGATION", label: "Yanlış rota" },
  { value: "PANIC", label: "Panik anı" },
  { value: "TEAM_EVENT", label: "Takım anı" },
  { value: "MILESTONE", label: "Kritik başarı" },
  { value: "SILENCE", label: "Sessiz felaket" },
  { value: "BETRAYAL", label: "Oyun içi ihanet" },
  { value: "MANUAL_NOTE", label: "Diğer oyun anı" },
];


function localId(): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  return `meme-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}


interface MemeGeneratorPanelProps {
  server: Server;
  members: Member[];
  currentUser: User;
  onClose: () => void;
}


export function MemeGeneratorPanel({
  server,
  members,
  currentUser,
  onClose,
}: MemeGeneratorPanelProps) {
  const [moment, setMoment] = useState<MemeMomentType>("FAILURE");
  const [targetId, setTargetId] = useState(currentUser.id);
  const [gameKey, setGameKey] = useState("manual");
  const [summary, setSummary] = useState("");
  const [setup, setSetup] = useState("");
  const [payoff, setPayoff] = useState("");
  const [job, setJob] = useState<MemeCandidateResponse | null>(null);
  const [rendered, setRendered] = useState<GeneratedMeme | null>(null);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const requestKey = useRef(localId());

  useEffect(() => () => {
    if (imageUrl) URL.revokeObjectURL(imageUrl);
  }, [imageUrl]);

  useEffect(() => {
    if (!job || !["QUEUED", "GENERATING"].includes(job.status)) return;
    const timer = window.setInterval(() => {
      void coreApi.getMemeCandidates(job.job_id).then(setJob).catch(() => undefined);
    }, 1_500);
    return () => window.clearInterval(timer);
  }, [job?.job_id, job?.status]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    setRendered(null);
    try {
      const accepted = await coreApi.createMemeJob(
        server.id,
        {
          event: {
            schema_version: "1.0",
            event_id: localId(),
            server_id: server.id,
            source: "MANUAL",
            occurred_at: new Date().toISOString(),
            moment_type: moment,
            actor_player_ids: [targetId],
            target_player_ids: [targetId],
            game: { game_key: gameKey.trim() },
            summary: summary.trim(),
            ...(setup.trim() ? { setup: setup.trim() } : {}),
            ...(payoff.trim() ? { payoff: payoff.trim() } : {}),
            importance: 0.9,
            confidence: 1,
            facts: [],
          },
          preferred_formats: [],
          desired_harshness: 1,
        },
        requestKey.current,
      );
      const next = await coreApi.getMemeCandidates(accepted.job_id);
      setJob(next);
      if (!accepted.meme_worthy) {
        setNotice(`Bu an güvenli kalite eşiğini geçmedi (${accepted.reasoning_code}).`);
      } else {
        setNotice("Üç güvenli caption adayı hazırlanıyor.");
      }
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Meme işi başlatılamadı.");
    } finally {
      setBusy(false);
    }
  }

  async function render(candidateId: string) {
    if (!job) return;
    setBusy(true);
    setError(null);
    try {
      const meme = await coreApi.renderMeme(job.job_id, candidateId);
      const blob = await coreApi.getMemeAsset(meme.asset_url);
      setImageUrl(URL.createObjectURL(blob));
      setRendered(meme);
      setNotice("Meme özel medya alanına kaydedildi.");
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Meme render edilemedi.");
    } finally {
      setBusy(false);
    }
  }

  async function feedback(type: "FUNNY" | "FORCED" | "TOO_HARSH" | "REPETITIVE" | "SAVE") {
    if (!rendered) return;
    try {
      await coreApi.submitMemeFeedback(rendered.id, type);
      setNotice("Geri bildirim kaydedildi.");
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Geri bildirim kaydedilemedi.");
    }
  }

  function reset() {
    setJob(null);
    setRendered(null);
    setImageUrl(null);
    setSummary("");
    setSetup("");
    setPayoff("");
    setNotice(null);
    requestKey.current = localId();
  }

  return (
    <div className="settings-overlay" onClick={onClose}>
      <section
        className="settings-panel settings-panel--wide meme-panel"
        onClick={(event) => event.stopPropagation()}
        aria-label="Meme Generator"
      >
        <header className="settings-panel__header">
          <div>
            <span className="panel-eyebrow">OYUN ANI → ÖZEL MEME</span>
            <h2>Meme Generator</h2>
          </div>
          <button className="settings-panel__close" onClick={onClose} aria-label="Kapat">
            <Icon name="close" />
          </button>
        </header>

        {error ? <div className="commentator-panel__message is-error">{error}</div> : null}
        {notice ? <div className="commentator-panel__message">{notice}</div> : null}

        {!job ? (
          <form className="meme-panel__form" onSubmit={submit}>
            <label>
              <span>An türü</span>
              <select value={moment} onChange={(event) => setMoment(event.target.value as MemeMomentType)}>
                {MOMENTS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
              </select>
            </label>
            <label>
              <span>İlgili oyuncu</span>
              <select value={targetId} onChange={(event) => setTargetId(Number(event.target.value))}>
                {members.map((member) => (
                  <option key={member.id} value={member.id}>{member.display_name || member.username}</option>
                ))}
              </select>
            </label>
            <label>
              <span>Oyun anahtarı</span>
              <input value={gameKey} maxLength={80} onChange={(event) => setGameKey(event.target.value)} required />
            </label>
            <label className="meme-panel__wide">
              <span>Gözlenen olay</span>
              <textarea value={summary} maxLength={240} onChange={(event) => setSummary(event.target.value)} required />
            </label>
            <label className="meme-panel__wide">
              <span>Kurulum <small>(isteğe bağlı)</small></span>
              <input value={setup} maxLength={160} onChange={(event) => setSetup(event.target.value)} />
            </label>
            <label className="meme-panel__wide">
              <span>Sonuç <small>(isteğe bağlı)</small></span>
              <input value={payoff} maxLength={160} onChange={(event) => setPayoff(event.target.value)} />
            </label>
            <p className="meme-panel__privacy">Yalnız sunucu üyeleri görür. AI yeni olay uyduramaz; oyuncu izinleri ve konu sınırları zorunludur.</p>
            <button type="submit" disabled={busy || !summary.trim() || !gameKey.trim()}>
              {busy ? "Sıraya alınıyor…" : "Caption adayları üret"}
            </button>
          </form>
        ) : null}

        {job ? (
          <section className="meme-panel__results">
            <header>
              <div><span>SKOR</span><strong>%{Math.round(job.meme_worthiness_score * 100)}</strong></div>
              <div><span>DURUM</span><strong>{job.status}</strong></div>
              <button type="button" onClick={reset}>Yeni an</button>
            </header>
            {job.status === "FAILED" ? <div className="commentator-panel__empty">Üretim güvenli biçimde durduruldu: {job.error_code}</div> : null}
            {["QUEUED", "GENERATING"].includes(job.status) ? <div className="commentator-panel__empty">AI Gateway caption adaylarını hazırlıyor…</div> : null}
            <div className="meme-panel__candidates">
              {job.candidates.map((candidate) => (
                <article key={candidate.id}>
                  <span>{candidate.template_name} · %{Math.round(candidate.quality_score * 100)}</span>
                  {Object.entries(candidate.captions).map(([zone, text]) => (
                    <p key={zone}><small>{zone}</small>{text}</p>
                  ))}
                  <button type="button" disabled={busy} onClick={() => void render(candidate.id)}>Bunu render et</button>
                </article>
              ))}
            </div>
          </section>
        ) : null}

        {rendered && imageUrl ? (
          <section className="meme-panel__artifact">
            <img src={imageUrl} alt="Üretilen özel oyun memesi" />
            <div>
              <strong>{rendered.template_name}</strong>
              <span>{Math.round(rendered.byte_size / 1024)} KB · özel PNG</span>
              <div className="commentator-panel__feedback">
                <button type="button" onClick={() => void feedback("FUNNY")}>Komik</button>
                <button type="button" onClick={() => void feedback("FORCED")}>Zorlama</button>
                <button type="button" onClick={() => void feedback("TOO_HARSH")}>Fazla sert</button>
                <button type="button" onClick={() => void feedback("REPETITIVE")}>Tekrarlı</button>
                <button type="button" onClick={() => void feedback("SAVE")}>Kaydet</button>
              </div>
            </div>
          </section>
        ) : null}
      </section>
    </div>
  );
}

