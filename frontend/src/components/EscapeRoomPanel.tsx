import { useEffect, useMemo, useRef, useState } from "react";

import { coreApi } from "../api/client";
import type { EscapeRoomNode, EscapeRoomView, Member, Server, User } from "../types";
import { Icon } from "./Icon";


const ROLE_LABELS = { ENGINEER: "Mühendis", ANALYST: "Analist", NAVIGATOR: "Navigatör" } as const;

function localId(prefix: string): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function clock(seconds: number): string {
  const minutes = Math.floor(seconds / 60).toString().padStart(2, "0");
  return `${minutes}:${(seconds % 60).toString().padStart(2, "0")}`;
}

interface EscapeRoomPanelProps { server: Server; members: Member[]; currentUser: User; onClose: () => void }

export function EscapeRoomPanel({ server, members, currentUser, onClose }: EscapeRoomPanelProps) {
  const [room, setRoom] = useState<EscapeRoomView | null>(null);
  const [players, setPlayers] = useState<number[]>([]);
  const [timerMode, setTimerMode] = useState<"RELAXED" | "STANDARD_45" | "CHALLENGE_30">("RELAXED");
  const [useLore, setUseLore] = useState(false);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [answer, setAnswer] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const createKey = useRef(localId("escape-session"));

  const selectedNode = useMemo(() => room?.nodes.find((node) => node.id === selectedNodeId) || null, [room?.nodes, selectedNodeId]);

  useEffect(() => setPlayers([currentUser.id, ...members.filter((member) => member.id !== currentUser.id).map((member) => member.id)].slice(0, 3)), [currentUser.id, members]);

  useEffect(() => {
    let cancelled = false; setLoading(true);
    coreApi.getActiveEscapeRoom(server.id).then((value) => { if (!cancelled) setRoom(value); }).catch((reason) => { if (!cancelled) setError(reason instanceof Error ? reason.message : "NADİR-3 yüklenemedi."); }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [server.id]);

  useEffect(() => {
    if (!room) return;
    const timer = window.setInterval(() => void coreApi.getEscapeRoom(room.session_id).then(setRoom).catch(() => undefined), 1_500);
    return () => window.clearInterval(timer);
  }, [room?.session_id]);

  useEffect(() => {
    if (!room) return;
    if (selectedNodeId && room.nodes.some((node) => node.id === selectedNodeId && node.status !== "LOCKED")) return;
    setSelectedNodeId(room.nodes.find((node) => node.status === "AVAILABLE")?.id || room.nodes.find((node) => node.status === "SOLVED")?.id || null);
  }, [room, selectedNodeId]);

  function togglePlayer(userId: number) {
    if (userId === currentUser.id) return;
    setPlayers((current) => current.includes(userId) ? current.filter((id) => id !== userId) : current.length < 3 ? [...current, userId] : current);
  }

  async function createRoom() {
    if (players.length !== 3) return;
    setBusy(true); setError(null);
    try { setRoom(await coreApi.createEscapeRoom(server.id, { player_ids: players, timer_mode: timerMode, use_party_lore: useLore }, createKey.current)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "NADİR-3 başlatılamadı."); }
    finally { setBusy(false); }
  }

  async function submit() {
    if (!room || !selectedNode?.submit_token || !answer.trim()) return;
    setBusy(true); setError(null); setNotice(null);
    try {
      const response = await coreApi.submitEscapeAnswer(room.session_id, selectedNode.id, { answer: answer.trim(), action_token: selectedNode.submit_token, expected_revision: room.revision }, localId("escape-attempt"));
      setRoom(response.view); setNotice(response.validator_result === "CORRECT" ? "Validator cevabı doğru kabul etti; durum commit edildi." : response.validator_result === "DUPLICATE" ? "Bu cevap daha önce aynı biçimde denendi; sayaç ve revizyon değişmedi." : "Cevap mekanizmayı açmadı.");
      if (response.validator_result === "CORRECT") setAnswer("");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Cevap doğrulanamadı."); }
    finally { setBusy(false); }
  }

  async function hint(node: EscapeRoomNode, tier: number) {
    if (!room || !node.hint_token) return;
    setBusy(true); setError(null);
    try { setRoom(await coreApi.requestEscapeHint(room.session_id, node.id, { tier, action_token: node.hint_token, expected_revision: room.revision })); setNotice(tier === 4 ? "Final Assist oyun kaydedildi; üç açık onay gerekli." : `Tier ${tier} hint yalnız senin konsoluna teslim edildi.`); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Hint alınamadı."); }
    finally { setBusy(false); }
  }

  return <div className="settings-panel-backdrop" onClick={onClose}>
    <section className="settings-panel settings-panel--wide escape-panel" onClick={(event) => event.stopPropagation()} aria-label="NADİR-3 Escape Room">
      <header className="settings-panel__header"><div><span className="panel-eyebrow">DETERMİNİSTİK PUZZLE GRAPH · ÖZEL KONSOLLAR</span><h2>NADİR-3 · Son Hava Kilidi</h2></div><button className="settings-panel__close" onClick={onClose} aria-label="Kapat"><Icon name="close" /></button></header>
      {loading ? <div className="commentator-panel__empty">Kontrol odası aranıyor…</div> : null}
      {error ? <div className="commentator-panel__message is-error">{error}</div> : null}
      {notice ? <div className="commentator-panel__message">{notice}</div> : null}

      {!loading && !room ? <section className="escape-panel__lobby"><h3>Tahliye ekibini oluştur</h3><p>Roller koltuk sırasıyla Mühendis, Analist ve Navigatör olur. Her oyuncu özel konsolunu yalnız kendi hesabından görür.</p><div>{members.map((member) => <label key={member.id} className={players.includes(member.id) ? "is-selected" : ""}><input type="checkbox" checked={players.includes(member.id)} disabled={member.id === currentUser.id} onChange={() => togglePlayer(member.id)}/>{member.display_name || member.username}</label>)}</div><label>Sayaç modu<select value={timerMode} onChange={(event) => setTimerMode(event.target.value as typeof timerMode)}><option value="RELAXED">Rahat · sayaç yok</option><option value="STANDARD_45">Standart · 45 dk</option><option value="CHALLENGE_30">Meydan okuma · 30 dk</option></select></label><label><input type="checkbox" checked={useLore} onChange={(event) => setUseLore(event.target.checked)}/>İzinli Party Lore'u yalnız atmosferde kullan</label><button type="button" disabled={busy || players.length !== 3} onClick={() => void createRoom()}>Hava kilidini aç</button></section> : null}

      {room ? <div className="escape-panel__room">
        <section className="escape-panel__topbar"><div><span>SÜRE</span><strong>{room.timer_mode === "RELAXED" ? "RAHAT" : clock(room.elapsed_seconds)}</strong></div><div><span>DURUM</span><strong>{room.overtime ? "OVERTIME" : room.status}</strong></div><div><span>ENVANTER</span><strong>{room.shared_inventory.length}</strong></div><div><span>ROLÜN</span><strong>{ROLE_LABELS[room.own_private.role]}</strong></div></section>
        <section className="escape-panel__players">{room.players.map((player) => <article key={player.user_id}><strong>{player.display_name}</strong><span>{ROLE_LABELS[player.role]}</span></article>)}</section>
        <div className="escape-panel__workspace">
          <section className="escape-panel__graph">{room.nodes.map((node) => <button key={node.id} type="button" disabled={node.status === "LOCKED"} className={`${node.status === "SOLVED" ? "is-solved" : node.status === "AVAILABLE" ? "is-available" : "is-locked"} ${selectedNodeId === node.id ? "is-selected" : ""}`} onClick={() => setSelectedNodeId(node.id)}><span>{node.id} · {node.kind}</span><strong>{node.title}</strong><small>{node.status}{node.kind === "META" ? ` · ${node.submitted_count}/3` : ""}</small></button>)}</section>
          <aside className="escape-panel__console"><span>ÖZEL {ROLE_LABELS[room.own_private.role].toUpperCase()} KONSOLU</span><h3>{selectedNode?.title || "Düğüm seç"}</h3>{selectedNode ? <><p>{room.own_private.clues[selectedNode.id] || "Bu düğüm için özel konsol verin yok; ekip arkadaşlarının ekranlarını sorun."}</p><dl><div><dt>Format</dt><dd>{selectedNode.answer_format}</dd></div><div><dt>Sahip</dt><dd>{selectedNode.owner_role}</dd></div><div><dt>Deneme</dt><dd>{selectedNode.attempt_count}</dd></div></dl>{selectedNode.status === "AVAILABLE" && selectedNode.submit_token ? <div className="escape-panel__answer"><input value={answer} maxLength={160} onChange={(event) => setAnswer(event.target.value)} placeholder={selectedNode.answer_format}/><button type="button" disabled={busy || !answer.trim()} onClick={() => void submit()}>Doğrula</button></div> : selectedNode.status === "AVAILABLE" ? <div className="commentator-panel__empty">Bu girişi ilgili konsol sahibi göndermeli veya senkron girdin zaten alındı.</div> : null}<div className="escape-panel__hints">{selectedNode.hint_token ? <><button type="button" disabled={busy} onClick={() => void hint(selectedNode, 1)}>Tier 1</button><button type="button" disabled={busy || selectedNode.attempt_count < 2} onClick={() => void hint(selectedNode, 2)}>Tier 2 · 2 hata</button><button type="button" disabled={busy || selectedNode.attempt_count < 4} onClick={() => void hint(selectedNode, 3)}>Tier 3 · 4 hata</button><button type="button" disabled={busy || selectedNode.attempt_count < 5} onClick={() => void hint(selectedNode, 4)}>Final Assist onayı</button></> : null}</div>{room.hints.filter((hintItem) => hintItem.node_id === selectedNode.id).map((hintItem) => <blockquote key={hintItem.tier}>Tier {hintItem.tier}: {hintItem.text}</blockquote>)}</> : null}</aside>
        </div>
        {room.host_messages.length ? <section className="escape-panel__host"><h3>AI Host</h3>{room.host_messages.slice(-6).reverse().map((message) => <p key={message.source_event_id}>{message.text}</p>)}</section> : <div className="commentator-panel__empty">AI Host hazırlanıyor. Mekanik bulmacalar ve deterministik hintler beklemeden kullanılabilir.</div>}
        {room.result ? <section className="escape-panel__result"><span>TAHLİYE TAMAMLANDI</span><h3>Derece {room.result.grade}</h3><p>{clock(room.result.elapsed_seconds)} · {room.result.optional_solved ? "Kaptan dolabı açıldı" : "Opsiyonel dolap kapalı"} · en yüksek hint Tier {room.result.max_hint_tier}</p></section> : null}
        <small className="escape-panel__proof">Graph/solution taahhüdü {room.rng_commitment.slice(0, 24)}… · cevaplar AI tarafından değerlendirilmez.</small>
      </div> : null}
    </section>
  </div>;
}
