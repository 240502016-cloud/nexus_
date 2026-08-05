import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";

import { ApiError, coreApi } from "../api/client";
import type { LoreCandidate, LoreEntry, Member, Server, User } from "../types";
import { Icon } from "./Icon";

const MODULES = [
  ["ai_commentator", "Yorumcu"], ["meme_generator", "Memeler"],
  ["highlight_generator", "Highlight"], ["ai_roast_battle", "Roast"],
  ["ai_board_game", "Son Portal"], ["hidden_role_game", "Üç Mühür"],
  ["shared_story", "Hikâye"], ["ai_escape_room", "Escape"],
] as const;

function newKey(): string {
  return typeof crypto.randomUUID === "function" ? crypto.randomUUID() : `lore-${Date.now()}-${Math.random()}`;
}

interface PartyLorePanelProps {
  server: Server;
  members: Member[];
  currentUser: User;
  onClose: () => void;
}

export function PartyLorePanel({ server, members, currentUser, onClose }: PartyLorePanelProps) {
  const [candidates, setCandidates] = useState<LoreCandidate[]>([]);
  const [entries, setEntries] = useState<LoreEntry[]>([]);
  const [title, setTitle] = useState("");
  const [summary, setSummary] = useState("");
  const [category, setCategory] = useState("moment");
  const [sensitivity, setSensitivity] = useState<"low" | "medium" | "high">("low");
  const [participants, setParticipants] = useState<number[]>([currentUser.id]);
  const [modules, setModules] = useState<string[]>(["ai_commentator", "meme_generator", "shared_story"]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const keyRef = useRef(newKey());
  const memberNames = useMemo(() => new Map(members.map((member) => [member.id, member.display_name || member.username])), [members]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [nextCandidates, nextEntries] = await Promise.all([
        coreApi.listLoreCandidates(server.id), coreApi.listLoreEntries(server.id),
      ]);
      setCandidates(nextCandidates);
      setEntries(nextEntries);
      setError(null);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Party Lore yüklenemedi.");
    } finally { setLoading(false); }
  }, [server.id]);

  useEffect(() => { void load(); }, [load]);

  function toggle(list: number[], value: number): number[] {
    return list.includes(value) ? list.filter((item) => item !== value) : [...list, value];
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!title.trim() || !summary.trim() || !participants.length || !modules.length) return;
    setBusy(true);
    try {
      await coreApi.createLoreCandidate(server.id, {
        title: title.trim(), summary: summary.trim(), participant_ids: participants,
        category: category.trim() || "moment", sensitivity, allowed_modules: modules,
      }, keyRef.current);
      keyRef.current = newKey();
      setTitle(""); setSummary("");
      await load();
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Lore adayı oluşturulamadı.");
    } finally { setBusy(false); }
  }

  async function review(candidateId: string, decision: "approved" | "rejected") {
    setBusy(true);
    try { await coreApi.reviewLoreCandidate(candidateId, decision); await load(); }
    catch (reason) { setError(reason instanceof ApiError ? reason.message : "Karar kaydedilemedi."); }
    finally { setBusy(false); }
  }

  async function remove(entryId: string) {
    setBusy(true);
    try { await coreApi.deleteLoreEntry(entryId); await load(); }
    catch (reason) { setError(reason instanceof ApiError ? reason.message : "Lore kaydı silinemedi."); }
    finally { setBusy(false); }
  }

  return <div className="settings-overlay" onClick={onClose}>
    <section className="settings-panel settings-panel--wide commentator-panel party-lore-panel" onClick={(event) => event.stopPropagation()} aria-label="Party Lore">
      <header className="settings-panel__header"><div><span className="panel-eyebrow">ORTAK HAFIZA · AÇIK RIZA</span><h2>Party Lore</h2></div><button className="settings-panel__close" onClick={onClose} aria-label="Kapat"><Icon name="close" /></button></header>
      {error ? <div className="commentator-panel__message is-error">{error}</div> : null}
      {loading ? <div className="commentator-panel__empty">Party Lore yükleniyor…</div> : null}
      {!loading ? <>
        <form className="commentator-panel__setup" onSubmit={submit}>
          <label><span>Başlık</span><input value={title} maxLength={120} onChange={(event) => setTitle(event.target.value)} placeholder="Ekibin hatırlamak isteyeceği an" /></label>
          <label><span>Tarafsız özet</span><textarea value={summary} maxLength={2000} onChange={(event) => setSummary(event.target.value)} placeholder="Olanı kısa, güvenli ve kişisel sınırları aşmadan anlatın." /></label>
          <div className="party-lore-panel__row"><label><span>Kategori</span><input value={category} maxLength={32} onChange={(event) => setCategory(event.target.value)} /></label><label><span>Hassasiyet</span><select value={sensitivity} onChange={(event) => setSensitivity(event.target.value as typeof sensitivity)}><option value="low">Düşük</option><option value="medium">Orta</option><option value="high">Yüksek</option></select></label></div>
          <fieldset><legend>Onayı gereken katılımcılar</legend>{members.map((member) => <label className="commentator-panel__player" key={member.id}><input type="checkbox" checked={participants.includes(member.id)} onChange={() => setParticipants((current) => toggle(current, member.id))}/><span>{member.display_name || member.username}</span></label>)}</fieldset>
          <fieldset><legend>Kullanmasına izin verilen modüller</legend><div className="party-lore-panel__modules">{MODULES.map(([key, label]) => <label className="commentator-panel__player" key={key}><input type="checkbox" checked={modules.includes(key)} onChange={() => setModules((current) => current.includes(key) ? current.filter((item) => item !== key) : [...current, key])}/><span>{label}</span></label>)}</div></fieldset>
          <button type="submit" disabled={busy || !title.trim() || !summary.trim() || !participants.length || !modules.length}>Onaya gönder</button>
        </form>
        <section className="party-lore-panel__list"><header><h3>Onay bekleyenler</h3><span>{candidates.length}</span></header>{candidates.length ? candidates.map((candidate) => { const mine = candidate.participants.find((participant) => participant.user_id === currentUser.id); return <article key={candidate.id}><div><strong>{candidate.title}</strong><small>{candidate.status} · {candidate.sensitivity} · {candidate.participants.map((participant) => memberNames.get(participant.user_id) || `#${participant.user_id}`).join(" · ")}</small><p>{candidate.summary}</p></div>{candidate.status === "pending" && mine?.decision === "pending" ? <footer><button disabled={busy} onClick={() => void review(candidate.id, "approved")}>Onayla</button><button disabled={busy} onClick={() => void review(candidate.id, "rejected")}>Reddet</button></footer> : null}</article>; }) : <p className="commentator-panel__empty">Bekleyen aday yok.</p>}</section>
        <section className="party-lore-panel__list"><header><h3>Onaylı ortak hafıza</h3><span>{entries.length}</span></header>{entries.length ? entries.map((entry) => <article key={entry.id}><div><strong>{entry.title}</strong><small>v{entry.version} · {entry.sensitivity} · {entry.allowed_modules.join(" · ")}</small><p>{entry.summary}</p></div>{entry.participant_ids.includes(currentUser.id) ? <footer><button disabled={busy} onClick={() => void remove(entry.id)}>Kaydı kaldır</button></footer> : null}</article>) : <p className="commentator-panel__empty">Henüz oybirliğiyle onaylanmış lore yok.</p>}</section>
      </> : null}
    </section>
  </div>;
}
