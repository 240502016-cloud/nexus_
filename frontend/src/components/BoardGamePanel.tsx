import { useEffect, useMemo, useRef, useState } from "react";

import { coreApi } from "../api/client";
import type { BoardGameAction, BoardGameView, Member, Server, User } from "../types";
import { Icon } from "./Icon";


const TILE_ORDER = ["E0", "E1", "E2", "E3", "T0", "T1", "T2", "T3", "G0", "G1", "G2", "G3", "P"];

function localId(prefix: string): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

interface BoardGamePanelProps {
  server: Server;
  members: Member[];
  currentUser: User;
  onClose: () => void;
}

export function BoardGamePanel({ server, members, currentUser, onClose }: BoardGamePanelProps) {
  const [game, setGame] = useState<BoardGameView | null>(null);
  const [players, setPlayers] = useState<number[]>([]);
  const [withAi, setWithAi] = useState(false);
  const [theme, setTheme] = useState<"ARCANE_RUINS" | "SPACE_WRECK" | "CURSED_CARNIVAL">("ARCANE_RUINS");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const createKey = useRef(localId("portal-session"));

  const memberMap = useMemo(() => new Map(members.map((member) => [member.id, member])), [members]);

  useEffect(() => {
    setPlayers([currentUser.id, ...members.filter((member) => member.id !== currentUser.id).map((member) => member.id)].slice(0, 3));
  }, [currentUser.id, members]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    coreApi.getActiveBoardGame(server.id)
      .then((value) => { if (!cancelled) setGame(value); })
      .catch((reason) => { if (!cancelled) setError(reason instanceof Error ? reason.message : "Son Portal yüklenemedi."); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [server.id]);

  useEffect(() => {
    if (!game || game.status !== "ACTIVE") return;
    const timer = window.setInterval(() => {
      void coreApi.getBoardGame(game.session_id).then(setGame).catch(() => undefined);
    }, 1_500);
    return () => window.clearInterval(timer);
  }, [game?.session_id, game?.status]);

  function togglePlayer(userId: number) {
    if (userId === currentUser.id) return;
    setPlayers((current) => current.includes(userId)
      ? current.filter((id) => id !== userId)
      : current.length < 3 ? [...current, userId] : current);
  }

  // AI ancak üçüncü koltuk boşken eklenebilir; toplam koltuk üçü aşamaz.
  const aiPlayers = players.length === 2 && withAi ? 1 : 0;
  const seatCount = players.length + aiPlayers;

  async function createGame() {
    if (players.length < 2) {
      setError("Son Portal en az iki oyuncu gerektirir.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      setGame(await coreApi.createBoardGame(server.id, { player_ids: players, ai_players: aiPlayers, theme }, createKey.current));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Oyun başlatılamadı.");
    } finally {
      setBusy(false);
    }
  }

  async function act(action: BoardGameAction) {
    if (!game) return;
    setBusy(true);
    setError(null);
    try {
      setGame(await coreApi.submitBoardGameAction(game.session_id, { action_id: action.id, action_token: action.token, expected_revision: game.revision }, localId("portal-action")));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Aksiyon uygulanamadı.");
      try { setGame(await coreApi.getBoardGame(game.session_id)); } catch { /* sonraki polling yeniler */ }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="settings-panel-backdrop" onClick={onClose}>
      <section className="settings-panel settings-panel--wide board-game-panel" onClick={(event) => event.stopPropagation()} aria-label="Son Portal masa oyunu">
        <header className="settings-panel__header">
          <div><span className="panel-eyebrow">DETERMİNİSTİK MOTOR · AI ANLATICI</span><h2>Son Portal</h2></div>
          <button className="settings-panel__close" onClick={onClose} aria-label="Kapat"><Icon name="close" /></button>
        </header>
        {loading ? <div className="commentator-panel__empty">Oyun aranıyor…</div> : null}
        {error ? <div className="commentator-panel__message is-error">{error}</div> : null}

        {!loading && !game ? (
          <section className="board-game-panel__lobby">
            <div><span>İki veya üç oyuncu seç</span><p>Kurallar sunucuda çalışır; AI yalnız gerçekleşmiş hamleleri anlatır ve erişilemezse oyun devam eder.</p></div>
            <div className="board-game-panel__member-grid">
              {members.map((member) => <label key={member.id} className={players.includes(member.id) ? "is-selected" : ""}><input type="checkbox" checked={players.includes(member.id)} disabled={member.id === currentUser.id} onChange={() => togglePlayer(member.id)} />{member.display_name || member.username}</label>)}
            </div>
            {players.length === 2 ? (
              <label className="board-game-panel__ai-toggle">
                <input type="checkbox" checked={withAi} onChange={(event) => setWithAi(event.target.checked)} />
                Üçüncü koltuğu AI oynasın
                <small>{withAi ? "Gezgin üçüncü oyuncu olur; hamleleri tohumdan belirlenir." : "İki kişilik masada tur başına 3 aksiyon puanı verilir."}</small>
              </label>
            ) : null}
            <label>Tema<select value={theme} onChange={(event) => setTheme(event.target.value as typeof theme)}><option value="ARCANE_RUINS">Gizemli Harabeler</option><option value="SPACE_WRECK">Uzay Enkazı</option><option value="CURSED_CARNIVAL">Lanetli Karnaval</option></select></label>
            <button type="button" disabled={busy || players.length < 2} onClick={() => void createGame()}>Masayı kur ({seatCount} koltuk)</button>
          </section>
        ) : null}

        {game ? (
          <div className="board-game-panel__game">
            <section className="board-game-panel__topbar">
              <div><span>TUR</span><strong>{game.round}/{game.maximum_rounds}</strong></div>
              <div><span>KAOS</span><strong>{game.chaos}/{game.chaos_limit}</strong></div>
              <div><span>PORTAL</span><strong>{game.portal_charge}/3</strong></div>
              <div><span>MÜHÜRLER</span><strong>{game.deposited_sigils.length}/3</strong></div>
              <div><span>AP</span><strong>{game.action_points}</strong></div>
            </section>

            <div className="board-game-panel__workspace">
              <section className="board-game-panel__board" aria-label="13 bölümlü Son Portal tahtası">
                {TILE_ORDER.map((tileId) => {
                  const tile = game.tiles[tileId];
                  const occupants = game.players.filter((player) => player.tile_id === tileId);
                  return <article key={tileId} className={`board-tile board-tile--${tile.region.toLowerCase()} ${tileId === "P" ? "board-tile--portal" : ""}`}><small>{tile.type}</small><strong>{tile.label}</strong><div>{occupants.map((player) => <span key={player.seat} title={player.display_name}>{player.ai ? "AI" : `P${player.seat + 1}`}</span>)}</div></article>;
                })}
              </section>

              <aside className="board-game-panel__rail">
                {game.players.map((player) => <article key={player.seat} className={game.active_seat === player.seat ? "is-active" : ""}><header><strong>{player.display_name}</strong><span>{player.ai ? "AI oyuncu" : memberMap.get(player.user_id ?? -1)?.username}</span></header><div><span>⚡ {player.energy}</span><span>🔩 {player.scrap}</span><span>★ {player.fame}</span><span>◆ {player.sigils.length}</span></div></article>)}
              </aside>
            </div>

            {game.status === "ACTIVE" ? (
              <section className="board-game-panel__actions">
                <header><div><span>AKTİF OYUNCU</span><strong>{game.players.find((player) => player.seat === game.active_seat)?.display_name}</strong></div>{game.active_user_id !== currentUser.id ? <p>{game.active_is_ai ? "Sıra AI oyuncuda; hamlesini kendi yapıyor." : "Sıra diğer oyuncuda. Ekran otomatik yenileniyor."}</p> : null}</header>
                <div>{game.legal_actions.map((action) => <button key={action.id} type="button" disabled={busy} onClick={() => void act(action)}><strong>{action.label}</strong><span>{action.cost}</span></button>)}</div>
              </section>
            ) : (
              <section className="board-game-panel__result"><span>{game.group_outcome}</span><h3>Kazanan: {game.players.find((player) => player.user_id !== null && player.user_id === game.winner_user_id)?.display_name ?? "AI oyuncu"}</h3><p>{game.end_reason}</p></section>
            )}

            <section className="board-game-panel__log">
              <h3>Oyun günlüğü</h3>
              <ol>{game.events.filter((item) => ["board.action_resolved", "board.narration_ready", "board.game_completed"].includes(item.type)).slice(-10).reverse().map((item) => <li key={item.id} className={item.type === "board.narration_ready" ? "is-narration" : ""}>{String(item.payload.text || item.payload.mechanical_summary || item.payload.group_outcome || item.type)}</li>)}</ol>
            </section>
            <small className="board-game-panel__proof">RNG taahhüdü: {game.rng_commitment.slice(0, 20)}… {game.rng_seed_reveal ? "· oyun sonu tohumu açıklandı" : ""}</small>
          </div>
        ) : null}
      </section>
    </div>
  );
}
