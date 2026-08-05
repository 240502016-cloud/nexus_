import { useEffect, useRef, useState } from "react";

import { coreApi } from "../api/client";
import type { Member, Server, SharedStoryView, StorySafetyProfile, User } from "../types";
import { Icon } from "./Icon";


function localId(prefix: string): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

interface SharedStoryPanelProps { server: Server; members: Member[]; currentUser: User; onClose: () => void }

export function SharedStoryPanel({ server, members, currentUser, onClose }: SharedStoryPanelProps) {
  const [story, setStory] = useState<SharedStoryView | null>(null);
  const [safety, setSafety] = useState<StorySafetyProfile | null>(null);
  const [players, setPlayers] = useState<number[]>([]);
  const [theme, setTheme] = useState<"MYSTERY" | "SURVIVAL" | "FANTASY">("FANTASY");
  const [length, setLength] = useState<"SHORT" | "STANDARD" | "LONG">("SHORT");
  const [useLore, setUseLore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const createKey = useRef(localId("story-session"));

  useEffect(() => setPlayers([currentUser.id, ...members.filter((member) => member.id !== currentUser.id).map((member) => member.id)].slice(0, 3)), [currentUser.id, members]);

  useEffect(() => {
    let cancelled = false; setLoading(true);
    Promise.all([coreApi.getStorySafetyProfile(server.id), coreApi.getActiveSharedStory(server.id)])
      .then(([profile, active]) => { if (!cancelled) { setSafety(profile); setStory(active); } })
      .catch((reason) => { if (!cancelled) setError(reason instanceof Error ? reason.message : "Ortak Hikâye yüklenemedi."); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [server.id]);

  useEffect(() => {
    if (!story) return;
    const timer = window.setInterval(() => void coreApi.getSharedStory(story.session_id).then(setStory).catch(() => undefined), 1_500);
    return () => window.clearInterval(timer);
  }, [story?.session_id]);

  function togglePlayer(userId: number) {
    if (userId === currentUser.id) return;
    setPlayers((current) => current.includes(userId) ? current.filter((id) => id !== userId) : current.length < 3 ? [...current, userId] : current);
  }

  async function saveSafety() {
    if (!safety) return;
    setBusy(true); setError(null);
    try {
      setSafety(await coreApi.updateStorySafetyProfile(server.id, { horror_level: safety.horror_level, violence_level: safety.violence_level, romance: safety.romance, player_conflict: safety.player_conflict, betrayal: safety.betrayal, personal_jokes: safety.personal_jokes, dark_humor: safety.dark_humor }));
      setNotice("Kişisel güvenlik sınırların kaydedildi.");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Sınırlar kaydedilemedi."); }
    finally { setBusy(false); }
  }

  async function createStory() {
    if (players.length !== 3) return;
    setBusy(true); setError(null);
    try { setStory(await coreApi.createSharedStory(server.id, { player_ids: players, theme, length, use_party_lore: useLore }, createKey.current)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Hikâye başlatılamadı."); }
    finally { setBusy(false); }
  }

  async function act(actionId: "INVESTIGATE" | "PROTECT" | "PRESS_ON") {
    if (!story?.action_token) return;
    setBusy(true); setError(null);
    try { setStory(await coreApi.submitStoryAction(story.session_id, { action_id: actionId, action_token: story.action_token, expected_revision: story.revision }, localId("story-action"))); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Sahne eylemi uygulanamadı."); }
    finally { setBusy(false); }
  }

  async function vote(choiceId: "STABILIZE" | "REVEAL_PATH" | "PUSH_FORWARD") {
    if (!story?.action_token) return;
    setBusy(true); setError(null);
    try { setStory(await coreApi.submitStoryVote(story.session_id, { choice_id: choiceId, action_token: story.action_token, expected_revision: story.revision })); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Ortak karar oyu gönderilemedi."); }
    finally { setBusy(false); }
  }

  return <div className="settings-panel-backdrop" onClick={onClose}>
    <section className="settings-panel settings-panel--wide story-panel" onClick={(event) => event.stopPropagation()} aria-label="Ortak Hikâye">
      <header className="settings-panel__header"><div><span className="panel-eyebrow">ÜÇ ODAK · TEK KADER · FAIL-FORWARD</span><h2>Ortak Hikâye</h2></div><button className="settings-panel__close" onClick={onClose} aria-label="Kapat"><Icon name="close" /></button></header>
      {loading ? <div className="commentator-panel__empty">Kayıtlı hikâye aranıyor…</div> : null}
      {error ? <div className="commentator-panel__message is-error">{error}</div> : null}
      {notice ? <div className="commentator-panel__message">{notice}</div> : null}

      {!loading && !story && safety ? <div className="story-panel__setup">
        <section className="story-panel__card"><span>1. KİŞİSEL SINIRLAR</span><h3>Güvenlik profilin</h3><p>Oturum, üç oyuncunun en kısıtlayıcı değerini kullanır; kimin hangi sınırı seçtiği paylaşılmaz.</p><label>Korku seviyesi<select value={safety.horror_level} onChange={(event) => setSafety({ ...safety, horror_level: Number(event.target.value) })}>{[0,1,2,3].map((value) => <option key={value}>{value}</option>)}</select></label><label>Şiddet seviyesi<select value={safety.violence_level} onChange={(event) => setSafety({ ...safety, violence_level: Number(event.target.value) })}>{[0,1,2,3].map((value) => <option key={value}>{value}</option>)}</select></label><label>Romantizm<select value={safety.romance} onChange={(event) => setSafety({ ...safety, romance: event.target.value as StorySafetyProfile["romance"] })}><option value="OFF">Kapalı</option><option value="SOFT">Yumuşak</option><option value="FADE_TO_BLACK">Fade to black</option></select></label><label><input type="checkbox" checked={safety.personal_jokes} onChange={(event) => setSafety({ ...safety, personal_jokes: event.target.checked })}/>Nazik kişisel şakalar</label><label><input type="checkbox" checked={safety.dark_humor} onChange={(event) => setSafety({ ...safety, dark_humor: event.target.checked })}/>Kara mizah</label><button type="button" disabled={busy} onClick={() => void saveSafety()}>Sınırlarımı kaydet</button></section>
        <section className="story-panel__card"><span>2. OTURUM</span><h3>Üç yolcuyu seç</h3><div className="story-panel__members">{members.map((member) => <label key={member.id} className={players.includes(member.id) ? "is-selected" : ""}><input type="checkbox" checked={players.includes(member.id)} disabled={member.id === currentUser.id} onChange={() => togglePlayer(member.id)}/>{member.display_name || member.username}</label>)}</div><label>Tema<select value={theme} onChange={(event) => setTheme(event.target.value as typeof theme)}><option value="FANTASY">Fantastik</option><option value="MYSTERY">Gizem</option><option value="SURVIVAL">Hayatta kalma</option></select></label><label>Uzunluk<select value={length} onChange={(event) => setLength(event.target.value as typeof length)}><option value="SHORT">Kısa · 2 bölüm</option><option value="STANDARD">Standart · 3 bölüm</option><option value="LONG">Uzun · 4 bölüm</option></select></label><label><input type="checkbox" checked={useLore} onChange={(event) => setUseLore(event.target.checked)}/>İzinli Party Lore'u yalnız dekoratif kurmaca esintisi olarak kullan</label><button type="button" disabled={busy || players.length !== 3} onClick={() => void createStory()}>Hikâyeyi başlat</button></section>
      </div> : null}

      {story ? <div className="story-panel__story">
        <section className="story-panel__hero"><span>{story.theme} · BÖLÜM {story.chapter}/{story.chapter_count}</span><h3>{story.title}</h3><p>{story.primary_goal}</p></section>
        <section className="story-panel__meters"><div><span>HEDEF</span><strong>{story.goal_progress}</strong></div><div><span>GİZEM</span><strong>{story.mystery_progress}</strong></div><div><span>TEHDİT</span><strong>{story.threat}/6</strong></div><div><span>BAĞ</span><strong>{story.bond}</strong></div></section>
        <section className="story-panel__characters">{story.characters.map((character) => <article key={character.user_id} className={story.active_user_id === character.user_id ? "is-active" : ""}><span>{character.archetype}</span><strong>{character.name}</strong><p>{character.traits.join(" · ")}</p><small>{character.location} · {character.inventory.join(", ")}</small></article>)}</section>
        <section className="story-panel__prose"><h3>Hikâye günlüğü</h3>{story.prose.length ? story.prose.slice(-8).map((item) => <article key={item.source_event_id}><span>{item.content_kind}</span><p>{item.text}</p>{item.lore_reference_ids.length ? <small>Kurmaca mesafesi uygulanmış Party Lore esintisi</small> : null}</article>) : <div className="commentator-panel__empty">Mekanik kurulum hazır. AI Gateway açılış metnini hazırlıyor; eylemler beklemeden kullanılabilir.</div>}</section>
        {story.phase === "SPOTLIGHT" ? <section className="story-panel__actions"><header><span>SPOTLIGHT</span><strong>{story.characters.find((character) => character.user_id === story.active_user_id)?.name}</strong></header>{story.active_user_id === currentUser.id ? <div>{story.spotlight_choices.map((choice) => <button key={choice.id} type="button" disabled={busy} onClick={() => void act(choice.id)}><strong>{choice.label}</strong><span>{choice.risk} RİSK</span></button>)}</div> : <p>Aktif karakterin mekanik seçimi bekleniyor.</p>}</section> : null}
        {story.phase === "JOINT_VOTE" ? <section className="story-panel__actions"><header><span>ORTAK KARAR</span><strong>Mühürlü oy · {story.submitted_vote_count}/3</strong></header>{story.action_token ? <div>{story.joint_choices.map((choice) => <button key={choice.id} type="button" disabled={busy} onClick={() => void vote(choice.id)}>{choice.label}</button>)}</div> : <p>Oyun alındı: {story.own_vote}. Diğer oyuncular bekleniyor.</p>}</section> : null}
        {story.ending_vector ? <section className="story-panel__ending"><span>SONUÇ VEKTÖRÜ</span><h3>{story.ending_vector.primary_goal}</h3><div>{Object.entries(story.ending_vector).map(([key, value]) => <p key={key}><strong>{key}</strong><span>{value}</span></p>)}</div><small>Final anlatısı AI tarafından yazılsa da bu sonuç motor tarafından kesinleştirildi.</small></section> : null}
        <small className="story-panel__proof">RNG taahhüdü {story.rng_commitment.slice(0, 24)}… · Güvenlik zarfı: korku {String(story.safety_envelope.horror_level)}, şiddet {String(story.safety_envelope.violence_level)}</small>
      </div> : null}
    </section>
  </div>;
}
