import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";

import { ApiError, coreApi } from "../api/client";
import type {
  CommentaryHistory,
  CommentaryIntensity,
  CommentarySession,
  CommentatorProfile,
  Member,
  Server,
  User,
} from "../types";
import { Icon } from "./Icon";


const EVENT_CATEGORIES = [
  "CLUTCH",
  "MILESTONE",
  "TEAMWORK",
  "ACCIDENTAL_SUCCESS",
  "REPEATED_MISTAKE",
  "PLAYER_DEATH",
  "PLAYER_FAIL",
  "MANUAL_NOTE",
] as const;

function localId(prefix: string): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function memberName(member: Member): string {
  return member.display_name || member.username;
}

interface CommentatorPanelProps {
  server: Server;
  members: Member[];
  currentUser: User;
  activeChannelId: number | null;
  onClose: () => void;
}

export function CommentatorPanel({
  server,
  members,
  currentUser,
  activeChannelId,
  onClose,
}: CommentatorPanelProps) {
  const [profiles, setProfiles] = useState<CommentatorProfile[]>([]);
  const [session, setSession] = useState<CommentarySession | null>(null);
  const [history, setHistory] = useState<CommentaryHistory | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [gameKey, setGameKey] = useState("manual");
  const [profileKey, setProfileKey] = useState("dry_sarcastic");
  const [intensity, setIntensity] = useState<CommentaryIntensity>("NORMAL");
  const [selectedPlayers, setSelectedPlayers] = useState<number[]>([]);
  const [category, setCategory] = useState<(typeof EVENT_CATEGORIES)[number]>("CLUTCH");
  const [summary, setSummary] = useState("");
  const createKeyRef = useRef(localId("commentator-session"));

  useEffect(() => {
    const defaults = [
      currentUser.id,
      ...members.filter((member) => member.id !== currentUser.id).map((member) => member.id),
    ].slice(0, 3);
    setSelectedPlayers(defaults);
  }, [currentUser.id, members]);

  const loadHistory = useCallback(async (sessionId: string) => {
    const next = await coreApi.getCommentaryHistory(sessionId);
    setHistory(next);
    setSession(next.session);
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([
      coreApi.listCommentatorProfiles(server.id),
      coreApi.getActiveCommentarySession(server.id),
    ])
      .then(async ([availableProfiles, activeSession]) => {
        if (cancelled) return;
        setProfiles(availableProfiles);
        setSession(activeSession);
        if (activeSession) await loadHistory(activeSession.id);
      })
      .catch((reason) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "Yorumcu yüklenemedi.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [loadHistory, server.id]);

  useEffect(() => {
    if (!session || session.status !== "active") return;
    const timer = window.setInterval(() => {
      void loadHistory(session.id).catch(() => undefined);
    }, 2_000);
    return () => window.clearInterval(timer);
  }, [loadHistory, session?.id, session?.status]);

  const memberMap = useMemo(
    () => new Map(members.map((member) => [member.id, memberName(member)])),
    [members],
  );

  function togglePlayer(userId: number) {
    setSelectedPlayers((current) => {
      if (userId === currentUser.id) return current;
      if (current.includes(userId)) return current.filter((id) => id !== userId);
      if (current.length >= 3) return current;
      return [...current, userId];
    });
  }

  async function createSession(event: FormEvent) {
    event.preventDefault();
    if (selectedPlayers.length !== 3) {
      setError("AI Commentator tam olarak üç oyuncu gerektirir.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const created = await coreApi.createCommentarySession(
        server.id,
        {
          game_key: gameKey.trim(),
          player_ids: selectedPlayers,
          profile_key: profileKey,
          intensity,
          text_to_speech_enabled: false,
          output_channel_id: activeChannelId,
        },
        createKeyRef.current,
      );
      setSession(created);
      await loadHistory(created.id);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Oturum başlatılamadı.");
    } finally {
      setBusy(false);
    }
  }

  async function toggleSilent() {
    if (!session) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await coreApi.updateCommentarySession(session.id, {
        expected_revision: session.revision,
        silent_mode: !session.silent_mode,
      });
      setSession(updated);
      setHistory((current) => (current ? { ...current, session: updated } : current));
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Sessiz mod değiştirilemedi.");
      await loadHistory(session.id).catch(() => undefined);
    } finally {
      setBusy(false);
    }
  }

  async function submitEvent(event: FormEvent) {
    event.preventDefault();
    if (!session || !summary.trim()) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await coreApi.postCommentatorEvent(session.id, {
        schema_version: "1.0",
        event_id: localId("manual-event"),
        source: "MANUAL",
        occurred_at: new Date().toISOString(),
        category,
        actor_player_ids: [currentUser.id],
        target_player_ids: category === "TEAMWORK" || category === "MILESTONE" ? [] : [currentUser.id],
        game: { game_key: session.game_key },
        importance: 0.9,
        confidence: 1,
        summary: summary.trim(),
        emotional_tone: "PLAYFUL",
        attributes: {},
      });
      setSummary("");
      setNotice(
        result.state === "PENDING"
          ? "Event kabul edildi; güvenli yorum üretimi sıraya alındı."
          : result.state === "DEDUPLICATED"
            ? "Bu event tekrar olarak filtrelendi."
            : "Event kaydedildi fakat deterministik filtre yorum üretmedi.",
      );
      await loadHistory(session.id);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Event gönderilemedi.");
    } finally {
      setBusy(false);
    }
  }

  async function sendFeedback(
    commentaryId: string,
    feedback: "FUNNY" | "NOT_FUNNY" | "TOO_HARSH" | "REPETITIVE",
  ) {
    setError(null);
    try {
      await coreApi.submitCommentaryFeedback(commentaryId, feedback);
      setNotice("Geri bildirim kaydedildi.");
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Geri bildirim kaydedilemedi.");
    }
  }

  async function endSession() {
    if (!session || !window.confirm("AI Commentator oturumu bitirilsin mi?")) return;
    setBusy(true);
    try {
      await coreApi.endCommentarySession(session.id, session.revision);
      setSession(null);
      setHistory(null);
      createKeyRef.current = localId("commentator-session");
      setNotice("Oturum sona erdi.");
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Oturum bitirilemedi.");
      await loadHistory(session.id).catch(() => undefined);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="settings-overlay" onClick={onClose}>
      <section
        className="settings-panel settings-panel--wide commentator-panel"
        onClick={(event) => event.stopPropagation()}
        aria-label="AI Commentator"
      >
        <header className="settings-panel__header">
          <div>
            <span className="panel-eyebrow">CANLI OYUN DENEYİMİ</span>
            <h2>AI Commentator</h2>
          </div>
          <button className="settings-panel__close" onClick={onClose} aria-label="Kapat">
            <Icon name="close" />
          </button>
        </header>

        {error ? <div className="commentator-panel__message is-error">{error}</div> : null}
        {notice ? <div className="commentator-panel__message">{notice}</div> : null}

        {loading ? <div className="commentator-panel__empty">Yorumcu yükleniyor…</div> : null}

        {!loading && !session ? (
          <form className="commentator-panel__setup" onSubmit={createSession}>
            <label>
              <span>Oyun anahtarı</span>
              <input value={gameKey} onChange={(event) => setGameKey(event.target.value)} required />
            </label>
            <label>
              <span>Yorumcu kişiliği</span>
              <select value={profileKey} onChange={(event) => setProfileKey(event.target.value)}>
                {profiles.map((profile) => (
                  <option key={profile.key} value={profile.key}>{profile.name}</option>
                ))}
              </select>
            </label>
            <label>
              <span>Yoğunluk</span>
              <select
                value={intensity}
                onChange={(event) => setIntensity(event.target.value as CommentaryIntensity)}
              >
                <option value="LOW">Düşük</option>
                <option value="NORMAL">Normal</option>
                <option value="HIGH">Yüksek</option>
              </select>
            </label>
            <fieldset>
              <legend>Üç oyuncu ({selectedPlayers.length}/3)</legend>
              {members.map((member) => (
                <label key={member.id} className="commentator-panel__player">
                  <input
                    type="checkbox"
                    checked={selectedPlayers.includes(member.id)}
                    disabled={member.id === currentUser.id}
                    onChange={() => togglePlayer(member.id)}
                  />
                  <span>{memberName(member)}</span>
                </label>
              ))}
            </fieldset>
            <button type="submit" disabled={busy || selectedPlayers.length !== 3 || !gameKey.trim()}>
              {busy ? "Başlatılıyor…" : "Oturumu başlat"}
            </button>
          </form>
        ) : null}

        {session ? (
          <>
            <div className="commentator-panel__status">
              <div>
                <span>{session.game_key}</span>
                <strong>{profiles.find((profile) => profile.key === session.profile_key)?.name ?? session.profile_key}</strong>
                <small>{session.player_ids.map((id) => memberMap.get(id) ?? `#${id}`).join(" · ")}</small>
              </div>
              <button
                type="button"
                className={session.silent_mode ? "is-silent" : ""}
                disabled={busy}
                onClick={() => void toggleSilent()}
              >
                {session.silent_mode ? "Sessiz modu kapat" : "Hemen sessize al"}
              </button>
            </div>

            <form className="commentator-panel__event-form" onSubmit={submitEvent}>
              <select value={category} onChange={(event) => setCategory(event.target.value as typeof category)}>
                {EVENT_CATEGORIES.map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
              <textarea
                value={summary}
                maxLength={240}
                onChange={(event) => setSummary(event.target.value)}
                placeholder="Yalnızca gözlemlenen oyun olayını kısa ve olgusal yazın…"
              />
              <button type="submit" disabled={busy || session.silent_mode || !summary.trim()}>
                Event gönder
              </button>
            </form>

            <section className="commentator-panel__history">
              <header>
                <div><span>CANLI AKIŞ</span><strong>Üretilen yorumlar</strong></div>
                <button type="button" onClick={() => void loadHistory(session.id)}>Yenile</button>
              </header>
              {history?.commentary.filter((item) => item.dispatch_state === "delivered").length ? (
                <ul>
                  {history.commentary
                    .filter((item) => item.dispatch_state === "delivered")
                    .slice()
                    .reverse()
                    .map((item) => (
                      <li key={item.id}>
                        <p>{item.commentary}</p>
                        <div>
                          <span>{item.tone} · %{Math.round(item.confidence * 100)}</span>
                          <span className="commentator-panel__feedback">
                            <button type="button" onClick={() => void sendFeedback(item.id, "FUNNY")}>İyi</button>
                            <button type="button" onClick={() => void sendFeedback(item.id, "NOT_FUNNY")}>Olmadı</button>
                            <button type="button" onClick={() => void sendFeedback(item.id, "TOO_HARSH")}>Sert</button>
                            <button type="button" onClick={() => void sendFeedback(item.id, "REPETITIVE")}>Tekrar</button>
                          </span>
                        </div>
                      </li>
                    ))}
                </ul>
              ) : (
                <div className="commentator-panel__empty">Henüz teslim edilen yorum yok.</div>
              )}
              <small>
                {history?.events.length ?? 0} event · {history?.commentary.length ?? 0} üretim kararı
              </small>
            </section>

            <button className="commentator-panel__end" type="button" disabled={busy} onClick={() => void endSession()}>
              Oturumu bitir
            </button>
          </>
        ) : null}
      </section>
    </div>
  );
}
