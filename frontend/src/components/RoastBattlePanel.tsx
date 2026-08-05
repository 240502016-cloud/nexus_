import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { coreApi } from "../api/client";
import type { Member, RoastProfile, RoastRound, RoastSession, RoastTopic, Server, User } from "../types";
import { Icon } from "./Icon";


const TOPICS: Array<{ value: RoastTopic; label: string }> = [
  { value: "FUNNY_HIGHLIGHTS", label: "Komik highlight'lar" },
  { value: "MATCH_STATISTICS", label: "Maç istatistikleri" },
  { value: "GAMING_MISTAKES", label: "Oyun hataları" },
  { value: "FAILED_STRATEGIES", label: "Başarısız stratejiler" },
  { value: "CONFIRMED_PARTY_LORE", label: "Onaylı Party Lore" },
  { value: "NAVIGATION", label: "Navigasyon" },
  { value: "TEAMWORK", label: "Takım oyunu" },
  { value: "INVENTORY", label: "Envanter" },
  { value: "TIMING", label: "Zamanlama" },
  { value: "REACTIONS", label: "Tepkiler" },
];

function localId(): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  return `roast-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function nameOf(member: Member | undefined, fallback: number): string {
  return member?.display_name || member?.username || `Oyuncu #${fallback}`;
}

interface RoastBattlePanelProps {
  server: Server;
  members: Member[];
  currentUser: User;
  onClose: () => void;
}

export function RoastBattlePanel({ server, members, currentUser, onClose }: RoastBattlePanelProps) {
  const [profile, setProfile] = useState<RoastProfile | null>(null);
  const [session, setSession] = useState<RoastSession | null>(null);
  const [round, setRound] = useState<RoastRound | null>(null);
  const [selectedPlayers, setSelectedPlayers] = useState<number[]>([]);
  const [requestedIntensity, setRequestedIntensity] = useState(1);
  const [blockedTerms, setBlockedTerms] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const createKey = useRef(localId());

  const memberMap = useMemo(
    () => new Map(members.map((member) => [member.id, member])),
    [members],
  );

  useEffect(() => {
    setSelectedPlayers([
      currentUser.id,
      ...members.filter((member) => member.id !== currentUser.id).map((member) => member.id),
    ].slice(0, 3));
  }, [currentUser.id, members]);

  const refreshSession = useCallback(async (sessionId: string) => {
    const nextSession = await coreApi.getRoastSession(sessionId);
    setSession(nextSession);
    if (nextSession.current_round > 0) {
      setRound(await coreApi.getCurrentRoastRound(sessionId));
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([coreApi.getRoastProfile(server.id), coreApi.getActiveRoastSession(server.id)])
      .then(async ([nextProfile, nextSession]) => {
        if (cancelled) return;
        setProfile(nextProfile);
        setBlockedTerms(nextProfile.blocked_terms.join(", "));
        setSession(nextSession);
        if (nextSession?.current_round) setRound(await coreApi.getCurrentRoastRound(nextSession.id));
      })
      .catch((reason) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "Roast Battle yüklenemedi.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [server.id]);

  useEffect(() => {
    if (!session || !["CONSENT_PENDING", "ACTIVE"].includes(session.status)) return;
    const timer = window.setInterval(() => {
      void refreshSession(session.id).catch(() => undefined);
    }, 1_500);
    return () => window.clearInterval(timer);
  }, [refreshSession, session?.id, session?.status]);

  function patchProfile(patch: Partial<RoastProfile>) {
    setProfile((current) => current ? { ...current, ...patch } : current);
  }

  function toggleTopic(topic: RoastTopic) {
    if (!profile) return;
    const next = profile.allowed_topics.includes(topic)
      ? profile.allowed_topics.filter((item) => item !== topic)
      : [...profile.allowed_topics, topic];
    patchProfile({ allowed_topics: next });
  }

  function togglePlayer(userId: number) {
    if (userId === currentUser.id) return;
    setSelectedPlayers((current) => current.includes(userId)
      ? current.filter((id) => id !== userId)
      : current.length < 3 ? [...current, userId] : current);
  }

  async function saveProfile() {
    if (!profile) return;
    setBusy(true);
    setError(null);
    try {
      const saved = await coreApi.updateRoastProfile(server.id, {
        roast_enabled: profile.roast_enabled,
        maximum_intensity: profile.maximum_intensity,
        allowed_topics: profile.allowed_topics,
        allow_party_lore: profile.allow_party_lore,
        allow_highlights: profile.allow_highlights,
        allow_recent_failures: profile.allow_recent_failures,
        blocked_terms: blockedTerms.split(",").map((item) => item.trim()).filter(Boolean),
      });
      setProfile(saved);
      setBlockedTerms(saved.blocked_terms.join(", "));
      setNotice("Kişisel roast sınırların kaydedildi.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Profil kaydedilemedi.");
    } finally {
      setBusy(false);
    }
  }

  async function createSession() {
    if (selectedPlayers.length !== 3) {
      setError("Roast Battle tam olarak üç oyuncu gerektirir.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const created = await coreApi.createRoastSession(
        server.id,
        { player_ids: selectedPlayers, requested_intensity: requestedIntensity },
        createKey.current,
      );
      setSession(created);
      setRound(null);
      setNotice("Oturum açıldı. Her oyuncu kendi hesabından onay vermeli.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Oturum oluşturulamadı.");
    } finally {
      setBusy(false);
    }
  }

  async function consent(decision: "READY" | "DECLINE" | "REVOKE") {
    if (!session || !profile) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await coreApi.submitRoastConsent(session.id, decision, profile.consent_version);
      setSession(updated);
      setNotice(decision === "READY" ? "Katılım onayın kaydedildi." : "Oturum güvenli biçimde kapatıldı.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Onay güncellenemedi.");
    } finally {
      setBusy(false);
    }
  }

  async function startRound() {
    if (!session) return;
    setBusy(true);
    setError(null);
    try {
      const next = await coreApi.startNextRoastRound(session.id);
      setRound(next);
      await refreshSession(session.id);
      if (next.status === "SKIPPED") {
        setNotice("Bu oyuncu için izinli ve doğrulanmış kaynak bulunamadı; tur AI çağrısı yapılmadan atlandı.");
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Tur başlatılamadı.");
    } finally {
      setBusy(false);
    }
  }

  async function vote(value: "FUNNY" | "OKAY" | "PASS") {
    if (!round?.candidate_id || !session) return;
    setBusy(true);
    setError(null);
    try {
      await coreApi.voteRoast(round.candidate_id, value);
      setNotice("Oyun kaydedildi. Diğer oyuncuların oyları bekleniyor.");
      await refreshSession(session.id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Oy kaydedilemedi.");
    } finally {
      setBusy(false);
    }
  }

  const ownConsent = session?.consent[currentUser.id];
  const canStartRound = session?.status === "ACTIVE" && (!round || ["COMPLETED", "SKIPPED"].includes(round.status)) && session.current_round < 3;

  return (
    <div className="settings-panel-backdrop" onClick={onClose}>
      <section className="settings-panel settings-panel--wide roast-panel" onClick={(event) => event.stopPropagation()} aria-label="AI Roast Battle">
        <header className="settings-panel__header">
          <div><span className="panel-eyebrow">AÇIK ONAY · DOĞRULANMIŞ OYUN OLAYI</span><h2>AI Roast Battle</h2></div>
          <button className="settings-panel__close" onClick={onClose} aria-label="Kapat"><Icon name="close" /></button>
        </header>

        {loading ? <div className="commentator-panel__empty">Roast ayarları yükleniyor…</div> : null}
        {error ? <div className="commentator-panel__message is-error">{error}</div> : null}
        {notice ? <div className="commentator-panel__message">{notice}</div> : null}

        {profile && !session ? (
          <div className="roast-panel__setup">
            <section className="roast-panel__card">
              <header><div><span>1. ADIM</span><h3>Kişisel sınırların</h3></div><label className="roast-panel__switch"><input type="checkbox" checked={profile.roast_enabled} onChange={(event) => patchProfile({ roast_enabled: event.target.checked })} />Roast'a izin ver</label></header>
              <label>En yüksek sertlik
                <select value={profile.maximum_intensity} onChange={(event) => patchProfile({ maximum_intensity: Number(event.target.value) })}>
                  <option value={0}>0 · Yumuşak</option><option value={1}>1 · Dengeli</option><option value={2}>2 · Cesur</option>
                </select>
              </label>
              <div className="roast-panel__topics">
                {TOPICS.map((topic) => <label key={topic.value}><input type="checkbox" checked={profile.allowed_topics.includes(topic.value)} onChange={() => toggleTopic(topic.value)} />{topic.label}</label>)}
              </div>
              <div className="roast-panel__permissions">
                <label><input type="checkbox" checked={profile.allow_highlights} onChange={(event) => patchProfile({ allow_highlights: event.target.checked })} />Highlight kullanımı</label>
                <label><input type="checkbox" checked={profile.allow_party_lore} onChange={(event) => patchProfile({ allow_party_lore: event.target.checked })} />Onaylı Party Lore kullanımı</label>
                <label><input type="checkbox" checked={profile.allow_recent_failures} onChange={(event) => patchProfile({ allow_recent_failures: event.target.checked })} />Yakın tarihli hatalar</label>
              </div>
              <label>Asla kullanılmayacak kelimeler<input value={blockedTerms} onChange={(event) => setBlockedTerms(event.target.value)} placeholder="virgülle ayır" /></label>
              <button type="button" disabled={busy} onClick={() => void saveProfile()}>Sınırlarımı kaydet</button>
            </section>

            <section className="roast-panel__card">
              <header><div><span>2. ADIM</span><h3>Üç kişilik masa</h3></div></header>
              <p className="roast-panel__help">Kendi hesabın otomatik seçilir. Her oyuncu kendi profilini açıp kendi hesabından ayrıca onay verir.</p>
              <div className="roast-panel__players">
                {members.map((member) => <label key={member.id} className={selectedPlayers.includes(member.id) ? "is-selected" : ""}><input type="checkbox" checked={selectedPlayers.includes(member.id)} disabled={member.id === currentUser.id} onChange={() => togglePlayer(member.id)} />{nameOf(member, member.id)}</label>)}
              </div>
              <label>Masa sertliği
                <select value={requestedIntensity} onChange={(event) => setRequestedIntensity(Number(event.target.value))}><option value={0}>Yumuşak</option><option value={1}>Dengeli</option><option value={2}>Cesur</option></select>
              </label>
              <button type="button" disabled={busy || !profile.roast_enabled || selectedPlayers.length !== 3} onClick={() => void createSession()}>Roast masasını aç</button>
            </section>
          </div>
        ) : null}

        {session ? (
          <div className="roast-panel__game">
            <section className="roast-panel__status">
              <div><span>OTURUM</span><strong>{session.status}</strong></div>
              <div><span>TUR</span><strong>{session.current_round} / 3</strong></div>
              <div><span>SERTLİK</span><strong>{session.requested_intensity}</strong></div>
            </section>
            <section className="roast-panel__consents">
              {session.player_ids.map((playerId) => <article key={playerId} className={`is-${session.consent[playerId]?.toLowerCase()}`}><strong>{nameOf(memberMap.get(playerId), playerId)}</strong><span>{session.consent[playerId]}</span></article>)}
            </section>

            {session.status === "CONSENT_PENDING" && ownConsent !== "READY" ? (
              <div className="roast-panel__actions"><button type="button" disabled={busy || !profile?.roast_enabled} onClick={() => void consent("READY")}>Kendi adıma onaylıyorum</button><button type="button" className="is-danger" disabled={busy} onClick={() => void consent("DECLINE")}>Katılmıyorum</button></div>
            ) : null}
            {session.status === "CONSENT_PENDING" && ownConsent === "READY" ? <div className="commentator-panel__empty">Diğer oyuncular kendi hesaplarından onay verdiğinde masa otomatik başlayacak.</div> : null}

            {round ? (
              <section className={`roast-panel__round is-${round.status.toLowerCase()}`}>
                <span>TUR {round.round_number} · HEDEF {nameOf(memberMap.get(round.target_player_id), round.target_player_id)}</span>
                {round.status === "GENERATING" ? <h3>AI Gateway güvenli adayları üretiyor ve bağımsız denetimden geçiriyor…</h3> : null}
                {round.status === "SKIPPED" ? <h3>İzinli, doğrulanmış kaynak bulunamadığı için bu tur atlandı.</h3> : null}
                {round.roast_text ? <blockquote>{round.roast_text}</blockquote> : null}
                {round.angle ? <small>{round.angle} · sertlik {round.effective_intensity}</small> : null}
                {round.status === "VOTING" ? <div className="roast-panel__votes"><button type="button" disabled={busy} onClick={() => void vote("FUNNY")}>😂 Komik</button><button type="button" disabled={busy} onClick={() => void vote("OKAY")}>🙂 İdare eder</button><button type="button" disabled={busy} onClick={() => void vote("PASS")}>Pas</button></div> : null}
              </section>
            ) : null}

            {canStartRound ? <button type="button" className="roast-panel__next" disabled={busy} onClick={() => void startRound()}>{session.current_round ? "Sonraki tur" : "İlk turu başlat"}</button> : null}
            {session.status === "ACTIVE" ? <button type="button" className="roast-panel__revoke" disabled={busy} onClick={() => void consent("REVOKE")}>Onayımı geri çek ve oturumu kapat</button> : null}
            {session.status === "ENDED" ? <div className="commentator-panel__empty">Üç tur tamamlandı. Roast Battle sona erdi.</div> : null}
            {session.status === "CANCELLED" ? <div className="commentator-panel__empty">Oturum bir oyuncunun kararıyla güvenli biçimde kapatıldı.</div> : null}
            <p className="roast-panel__help">Kaynak için önce Highlight, AI Commentator veya izinli Party Lore içinde oyuncuya bağlı doğrulanmış bir oyun olayı bulunmalı.</p>
          </div>
        ) : null}
      </section>
    </div>
  );
}
