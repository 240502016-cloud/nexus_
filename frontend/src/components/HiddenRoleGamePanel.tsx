import { useEffect, useRef, useState } from "react";

import { coreApi } from "../api/client";
import type { HiddenRoleGameView, Member, Server, User } from "../types";
import { Icon } from "./Icon";


const OFFICE_LABELS = { SENTINEL: "Muhafız", ARCHIVIST: "Arşivci", ENVOY: "Elçi" } as const;
const MANDATE_LABELS = { SEAL: "Mühürle", REVEAL: "Açığa Çıkar", REDIRECT: "Yönlendir" } as const;
const OBJECTIVE_LABELS: Record<string, string> = {
  SAFE_THREE: "En az üç güvenli oy kullan",
  SUPPORTED_THREE: "En az üç desteklenen iddia yap",
  VARIED_VOTES: "Üç farklı karar türünü kullan",
  REPUTATION_THREE: "Oyunu en az 3 itibarla bitir",
};

function localId(): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  return `hidden-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

interface HiddenRoleGamePanelProps { server: Server; members: Member[]; currentUser: User; onClose: () => void }

export function HiddenRoleGamePanel({ server, members, currentUser, onClose }: HiddenRoleGamePanelProps) {
  const [game, setGame] = useState<HiddenRoleGameView | null>(null);
  const [players, setPlayers] = useState<number[]>([]);
  const [claimOption, setClaimOption] = useState<"A" | "B" | "C">("A");
  const [proposition, setProposition] = useState("EXCLUDES_SAFE");
  const [flavor, setFlavor] = useState("");
  const [withAi, setWithAi] = useState(false);
  // Tahminler katılımcı anahtarıyla tutulur: insan için "12", AI koltuğu için "ai:2".
  const [officeGuesses, setOfficeGuesses] = useState<Record<string, string>>({});
  const [mandateGuesses, setMandateGuesses] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const createKey = useRef(localId());
  useEffect(() => setPlayers([currentUser.id, ...members.filter((member) => member.id !== currentUser.id).map((member) => member.id)].slice(0, 3)), [currentUser.id, members]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    coreApi.getActiveHiddenRoleGame(server.id).then((value) => { if (!cancelled) setGame(value); }).catch((reason) => { if (!cancelled) setError(reason instanceof Error ? reason.message : "Üç Mühür yüklenemedi."); }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [server.id]);

  useEffect(() => {
    if (!game || (game.status === "COMPLETED" && game.recap)) return;
    const timer = window.setInterval(() => void coreApi.getHiddenRoleGame(game.session_id).then(setGame).catch(() => undefined), 1_500);
    return () => window.clearInterval(timer);
  }, [game?.session_id, game?.status, game?.recap]);

  useEffect(() => {
    if (!game || game.phase !== "FINAL_DEDUCTION") return;
    const others = game.players.filter((player) => player.user_id !== currentUser.id);
    setOfficeGuesses((current) => Object.keys(current).length ? current : Object.fromEntries(others.map((player) => [player.key, "SENTINEL"])));
    setMandateGuesses((current) => Object.keys(current).length ? current : Object.fromEntries(others.map((player) => [player.key, "SEAL"])));
  }, [currentUser.id, game?.phase, game?.players]);

  function togglePlayer(userId: number) {
    if (userId === currentUser.id) return;
    setPlayers((current) => current.includes(userId) ? current.filter((id) => id !== userId) : current.length < 3 ? [...current, userId] : current);
  }

  // AI ancak üçüncü koltuk boşken eklenebilir.
  const aiPlayers = players.length === 2 && withAi ? 1 : 0;

  async function createGame() {
    if (players.length < 2) { setError("Üç Mühür en az iki oyuncu gerektirir."); return; }
    setBusy(true); setError(null);
    try { setGame(await coreApi.createHiddenRoleGame(server.id, players, aiPlayers, createKey.current)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Oyun oluşturulamadı."); }
    finally { setBusy(false); }
  }

  async function submitClaim() {
    if (!game?.legal_action) return;
    setBusy(true); setError(null);
    try { setGame(await coreApi.submitHiddenRoleClaim(game.session_id, { subject_option_id: claimOption, proposition, flavor_text: flavor.trim(), action_token: game.legal_action.token, expected_revision: game.revision })); setFlavor(""); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "İddia gönderilemedi."); }
    finally { setBusy(false); }
  }

  async function submitVote(optionId: "A" | "B" | "C") {
    if (!game?.legal_action) return;
    setBusy(true); setError(null);
    try { setGame(await coreApi.submitHiddenRoleVote(game.session_id, { option_id: optionId, action_token: game.legal_action.token, expected_revision: game.revision })); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Oy mühürlenemedi."); }
    finally { setBusy(false); }
  }

  async function submitDeduction() {
    if (!game?.legal_action) return;
    setBusy(true); setError(null);
    try { setGame(await coreApi.submitHiddenRoleDeduction(game.session_id, { office_by_key: officeGuesses, mandate_by_key: mandateGuesses, action_token: game.legal_action.token, expected_revision: game.revision })); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Final tahmini gönderilemedi."); }
    finally { setBusy(false); }
  }

  return <div className="settings-panel-backdrop" onClick={onClose}>
    <section className="settings-panel settings-panel--wide hidden-role-panel" onClick={(event) => event.stopPropagation()} aria-label="Üç Mühür Protokolü">
      <header className="settings-panel__header"><div><span className="panel-eyebrow">ŞİFRELİ GİZLİ BİLGİ · İKİ VEYA ÜÇ OYUNCU</span><h2>Üç Mühür Protokolü</h2></div><button className="settings-panel__close" onClick={onClose} aria-label="Kapat"><Icon name="close" /></button></header>
      {loading ? <div className="commentator-panel__empty">Gizli oturum aranıyor…</div> : null}
      {error ? <div className="commentator-panel__message is-error">{error}</div> : null}

      {!loading && !game ? <section className="hidden-role-panel__lobby"><h3>İki veya üç oyuncu seç</h3><p>Her oyuncu kendi tarayıcı oturumundan yalnız kendi rolünü, talimatını ve ipucunu görür.</p><div>{members.map((member) => <label key={member.id} className={players.includes(member.id) ? "is-selected" : ""}><input type="checkbox" checked={players.includes(member.id)} disabled={member.id === currentUser.id} onChange={() => togglePlayer(member.id)} />{member.display_name || member.username}</label>)}</div>{players.length === 2 ? <label className="hidden-role-panel__ai-toggle"><input type="checkbox" checked={withAi} onChange={(event) => setWithAi(event.target.checked)} />Üçüncü koltuğu AI (Vekil) doldursun<small>{withAi ? "Vekil'in gizli rolü de tahmin edilecek koltuklara dahil olur." : "İki koltuklu konseyde beraberlikte hakem koltuğu karar verir."}</small></label> : null}<button type="button" disabled={busy || players.length < 2} onClick={() => void createGame()}>Protokolü başlat</button></section> : null}

      {game ? <div className="hidden-role-panel__game">
        <section className="hidden-role-panel__topbar"><div><span>KRİZ</span><strong>{game.round}/4</strong></div><div><span>FAZ</span><strong>{game.phase}</strong></div><div><span>İSTİKRAR</span><strong>{game.stability}/5</strong></div></section>

        {game.status === "ACTIVE" ? <section className="hidden-role-panel__secret"><span>YALNIZ SEN GÖRÜYORSUN</span><div><strong>{OFFICE_LABELS[game.own_private.office]}</strong><strong>Talimat: {MANDATE_LABELS[game.own_private.mandate]}</strong></div><p>{OBJECTIVE_LABELS[game.own_private.objective] || game.own_private.objective}</p>{game.own_private.clue ? <blockquote>{game.own_private.clue}</blockquote> : null}</section> : null}

        {game.crisis ? <section className="hidden-role-panel__crisis"><span>{game.crisis.key}</span><h3>{game.crisis.title}</h3><p>{game.crisis.brief}</p><blockquote>{game.crisis.public_clue}</blockquote><div>{game.crisis.options.map((option) => <article key={option.id}><b>{option.id}</b><strong>{option.title}</strong><span>{MANDATE_LABELS[option.disposition]}</span></article>)}</div></section> : null}

        <section className="hidden-role-panel__players">{game.players.map((player) => <article key={player.key} className={player.ai ? "is-ai" : ""}><strong>{player.display_name}</strong><span>İtibar {player.reputation} · İçgörü {player.insight}</span></article>)}</section>

        {game.phase === "CLAIM" && game.legal_action?.kind === "CLAIM" ? <section className="hidden-role-panel__command"><h3>Yapılandırılmış iddian</h3><div><label>Seçenek<select value={claimOption} onChange={(event) => setClaimOption(event.target.value as typeof claimOption)}><option>A</option><option>B</option><option>C</option></select></label><label>Önerme<select value={proposition} onChange={(event) => setProposition(event.target.value)}><option value="SUPPORTS_SAFE">Güvenliyi destekliyor</option><option value="EXCLUDES_SAFE">Güvenli olamaz</option><option value="RISK_HIGH">Riski yüksek</option><option value="RISK_LOW">Riski düşük</option></select></label></div><textarea value={flavor} maxLength={240} onChange={(event) => setFlavor(event.target.value)} placeholder="İsteğe bağlı, mekanik puanı değiştirmeyen ifade"/><button type="button" disabled={busy} onClick={() => void submitClaim()}>İddiayı yayınla</button></section> : null}
        {game.phase === "CLAIM" && !game.legal_action ? <div className="commentator-panel__empty">Diğer oyuncuların iddiaları bekleniyor.</div> : null}

        {game.claims.length ? <section className="hidden-role-panel__claims"><h3>Açık iddialar</h3>{game.claims.map((claim) => <article key={claim.key}><strong>{game.players.find((player) => player.key === claim.key)?.display_name}</strong><span>{claim.subject_option_id} · {claim.proposition}{claim.verdict ? ` · ${claim.verdict}` : ""}</span><p>{claim.flavor_text}</p></article>)}</section> : null}

        {game.phase === "VOTE" && game.legal_action?.kind === "VOTE" ? <section className="hidden-role-panel__command"><h3>Mühürlü oyun</h3><p>Seçimin diğer üç oy tamamlanana kadar yalnız sana görünür.</p><div className="hidden-role-panel__vote-buttons">{game.crisis?.options.map((option) => <button key={option.id} type="button" disabled={busy} onClick={() => void submitVote(option.id)}>{option.id} · {option.title}</button>)}</div></section> : null}
        {game.phase === "VOTE" && !game.legal_action ? <div className="commentator-panel__empty">Oyun mühürlendi ({game.submitted_vote_count}/{game.human_player_count}). Diğer oylar bekleniyor.</div> : null}

        {game.phase === "FINAL_DEDUCTION" && game.legal_action?.kind === "DEDUCTION" ? <section className="hidden-role-panel__command"><h3>Final rol eşleştirmen</h3>{game.players.filter((player) => player.user_id !== currentUser.id).map((player) => <div key={player.key} className="hidden-role-panel__guess"><strong>{player.display_name}</strong><select value={officeGuesses[player.key] || "SENTINEL"} onChange={(event) => setOfficeGuesses((current) => ({ ...current, [player.key]: event.target.value }))}>{Object.entries(OFFICE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select><select value={mandateGuesses[player.key] || "SEAL"} onChange={(event) => setMandateGuesses((current) => ({ ...current, [player.key]: event.target.value }))}>{Object.entries(MANDATE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>)}<button type="button" disabled={busy} onClick={() => void submitDeduction()}>Tahminleri mühürle</button></section> : null}
        {game.phase === "FINAL_DEDUCTION" && !game.legal_action ? <div className="commentator-panel__empty">Final tahminin alındı ({game.submitted_deduction_count}/{game.human_player_count}).</div> : null}

        {game.result ? <section className="hidden-role-panel__result"><span>{game.result.group_outcome}</span><h3>Kazanan: {game.players.find((player) => player.key === game.result?.winner_key)?.display_name}</h3><div>{[...game.result.scores].sort((a, b) => b.total - a.total).map((score) => <article key={score.key}><strong>{game.players.find((player) => player.key === score.key)?.display_name} · {score.total} puan</strong><span>{game.result?.assignments[score.key]?.office} / {game.result?.assignments[score.key]?.mandate}</span></article>)}</div>{game.recap ? <blockquote>{game.recap}</blockquote> : <p>AI Gateway final özeti hazırlanıyor; sonuç zaten kesindir.</p>}</section> : null}
        <small className="hidden-role-panel__proof">Atama taahhüdü: {game.rng_commitment.slice(0, 24)}…</small>
      </div> : null}
    </section>
  </div>;
}
