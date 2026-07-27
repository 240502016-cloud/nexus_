import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";

import type { Channel, Message } from "../types";

const GAME_EVENT_PREFIX = "NEXUS_GAME_EVENT:";

interface GameMessageEvent {
  type: string;
  challenge_id?: string;
  game?: string;
  game_label?: string;
  challenger?: string;
  opponent?: string;
  result?: string;
  winner?: string | null;
  entry_count?: number;
}

interface ParsedGameMessage {
  event: GameMessageEvent;
  body: string;
}

interface ChatAreaProps {
  channel: Channel | undefined;
  messages: Message[];
  currentMatrixUserId: string | null;
  onSendMessage: (content: string) => Promise<void>;
  onDeleteMessage: (eventId: string) => void;
  onRetryMessage: (clientId: string, content: string) => void;
  hasMoreMessages: boolean;
  loadingOlder: boolean;
  onLoadOlder: () => Promise<void>;
}

function displayName(matrixUserId: string): string {
  // "@aylin:nexus.local" -> "aylin"
  return matrixUserId.replace(/^@/, "").split(":")[0];
}

function parseGameMessage(content: string): ParsedGameMessage | null {
  if (!content.startsWith(GAME_EVENT_PREFIX)) return null;
  const [header, ...bodyLines] = content.split("\n");
  try {
    const event = JSON.parse(header.slice(GAME_EVENT_PREFIX.length)) as GameMessageEvent;
    if (!event || typeof event.type !== "string") return null;
    return { event, body: bodyLines.join("\n") };
  } catch {
    return null;
  }
}

function gameCardTitle(event: GameMessageEvent): string {
  if (event.type === "invite") return "Düello daveti";
  if (event.type === "accepted") return "Karşılaşma başladı";
  if (event.type === "move_locked") return "Hamle kilitlendi";
  if (event.type === "result" && event.game === "rps") return "Hamleler açıldı";
  if (event.type === "result" && event.game === "coin") return "Yazı · Tura";
  if (event.type === "wheel_result") return "Çarkıfelek sonucu";
  if (event.type === "wheel_updated") return "Çark güncellendi";
  if (event.type === "rejected") return "Davet reddedildi";
  if (event.type === "cancelled") return "Davet iptal edildi";
  if (event.type === "expired") return "Süre doldu";
  return "Şans Ustası";
}

export function ChatArea({
  channel,
  messages,
  currentMatrixUserId,
  onSendMessage,
  onDeleteMessage,
  onRetryMessage,
  hasMoreMessages,
  loadingOlder,
  onLoadOlder,
}: ChatAreaProps) {
  const [draft, setDraft] = useState("");
  const [gameActionBusy, setGameActionBusy] = useState<string | null>(null);
  const [unseenMessageCount, setUnseenMessageCount] = useState(0);
  const messagesRef = useRef<HTMLDivElement | null>(null);
  const historyRequestRef = useRef(false);
  const knownMessageIdsRef = useRef<Set<string>>(new Set());
  const initializedChannelRef = useRef<number | null>(null);
  const isNearBottomRef = useRef(true);
  const forceScrollToBottomRef = useRef(false);

  function scrollToLatest(behavior: ScrollBehavior = "smooth") {
    const container = messagesRef.current;
    if (!container) return;
    container.scrollTo({ top: container.scrollHeight, behavior });
    isNearBottomRef.current = true;
    setUnseenMessageCount(0);
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const content = draft.trim();
    if (!content) return;
    // Input'u ağ yanıtını beklemeden temizle; App mesajı aynı anda iyimser olarak listeye ekler.
    setDraft("");
    forceScrollToBottomRef.current = true;
    await onSendMessage(content);
  }

  // API mesajları yeniden eskiye döner; sohbet için eskiden yeniye çeviriyoruz.
  const ordered = [...messages].reverse();
  const parsedMessages = ordered.map((message) => ({
    message,
    // Yapılandırılmış kart protokolü yalnızca backend'in doğruladığı gerçek bot mesajlarında
    // yorumlanır; normal kullanıcı aynı prefix'i yazarak sahte davet kartı üretemez.
    gameMessage: message.is_bot ? parseGameMessage(message.content) : null,
  }));
  const resolvedChallengeIds = new Set(
    parsedMessages
      .filter(({ gameMessage }) =>
        ["accepted", "result", "rejected", "cancelled", "expired"].includes(
          gameMessage?.event.type ?? "",
        ),
      )
      .map(({ gameMessage }) => gameMessage?.event.challenge_id)
      .filter((id): id is string => Boolean(id)),
  );
  const currentUsername = currentMatrixUserId ? displayName(currentMatrixUserId).toLocaleLowerCase("tr") : "";

  useEffect(() => {
    knownMessageIdsRef.current = new Set();
    initializedChannelRef.current = channel?.id ?? null;
    isNearBottomRef.current = true;
    forceScrollToBottomRef.current = false;
    setUnseenMessageCount(0);
  }, [channel?.id]);

  useEffect(() => {
    if (!channel || messages.length === 0) return;
    const knownIds = knownMessageIdsRef.current;

    // İlk kanal yüklemesinde doğrudan en güncel mesaja git.
    if (knownIds.size === 0 && initializedChannelRef.current === channel.id) {
      knownMessageIdsRef.current = new Set(messages.map((message) => message.event_id));
      requestAnimationFrame(() => scrollToLatest("auto"));
      return;
    }

    // Yeni mesajlar listenin başına eklenir; lazy-load edilen eski mesajlar sona eklendiği için
    // burada bildirim üretmez. Silme işlemi de mevcut bir kimliği öne taşıdığı için yeni sayılmaz.
    const newest = messages[0];
    const isNewHead = !knownIds.has(newest.event_id);
    knownMessageIdsRef.current = new Set(messages.map((message) => message.event_id));
    if (!isNewHead) return;

    const ownMessage =
      newest.sender === currentMatrixUserId ||
      Boolean(newest.delivery_status) ||
      forceScrollToBottomRef.current;
    forceScrollToBottomRef.current = false;

    if (ownMessage || isNearBottomRef.current) {
      requestAnimationFrame(() => scrollToLatest(ownMessage ? "smooth" : "auto"));
    } else {
      setUnseenMessageCount((count) => count + 1);
    }
  }, [channel, currentMatrixUserId, messages]);

  async function runGameAction(challengeId: string, command: string) {
    setGameActionBusy(`${challengeId}:${command}`);
    try {
      await onSendMessage(command);
    } finally {
      setGameActionBusy(null);
    }
  }

  async function loadOlderPreservingScroll() {
    const container = messagesRef.current;
    if (!container || !hasMoreMessages || loadingOlder || historyRequestRef.current) return;
    historyRequestRef.current = true;
    const previousHeight = container.scrollHeight;
    const previousTop = container.scrollTop;
    try {
      await onLoadOlder();
      requestAnimationFrame(() => {
        container.scrollTop = previousTop + (container.scrollHeight - previousHeight);
      });
    } finally {
      historyRequestRef.current = false;
    }
  }

  return (
    <section className="chat-area">
      <header className="chat-area__header">
        {channel ? `${channel.type === "voice" ? "🔊" : "#"} ${channel.name}` : "Bir kanal seçin"}
      </header>
      <div
        className="chat-area__messages"
        aria-live="polite"
        ref={messagesRef}
        onScroll={(event) => {
          const container = event.currentTarget;
          const nearBottom = container.scrollHeight - container.scrollTop - container.clientHeight <= 64;
          isNearBottomRef.current = nearBottom;
          if (nearBottom && unseenMessageCount > 0) setUnseenMessageCount(0);
          if (event.currentTarget.scrollTop <= 64) void loadOlderPreservingScroll();
        }}
      >
        {channel && hasMoreMessages ? (
          <button
            type="button"
            className="chat-area__load-older"
            disabled={loadingOlder}
            onClick={() => void loadOlderPreservingScroll()}
          >
            {loadingOlder ? "Eski mesajlar yükleniyor…" : "Daha eski mesajları yükle"}
          </button>
        ) : null}
        {!channel ? null : ordered.length === 0 ? (
          <p className="chat-area__placeholder">Henüz mesaj yok. İlk mesajı sen yaz.</p>
        ) : (
          parsedMessages.map(({ message, gameMessage }) => {
            const own = message.sender === currentMatrixUserId || Boolean(message.delivery_status);
            const className = [
              "chat-message",
              own ? "chat-message--own" : "",
              message.delivery_status === "sending" ? "chat-message--sending" : "",
              message.delivery_status === "failed" ? "chat-message--failed" : "",
            ]
              .filter(Boolean)
              .join(" ");
            return (
              <div key={message.event_id} className={className}>
                <span className="chat-message__sender">{displayName(message.sender)}</span>
                {gameMessage ? (
                  <div
                    className={`chance-card chance-card--${gameMessage.event.game ?? gameMessage.event.type}`}
                  >
                    <div className="chance-card__eyebrow">
                      <span className="chance-card__icon">
                        {gameMessage.event.game === "wheel"
                          ? "🎡"
                          : gameMessage.event.game === "coin"
                            ? "🪙"
                            : "🎲"}
                      </span>
                      {gameCardTitle(gameMessage.event)}
                    </div>
                    <div className="chance-card__body">{gameMessage.body}</div>
                    {gameMessage.event.type === "invite" && gameMessage.event.challenge_id ? (
                      resolvedChallengeIds.has(gameMessage.event.challenge_id) ? (
                        <span className="chance-card__status">Davet yanıtlandı</span>
                      ) : gameMessage.event.opponent?.toLocaleLowerCase("tr") === currentUsername ? (
                        <div className="chance-card__actions">
                          <button
                            type="button"
                            disabled={gameActionBusy !== null}
                            onClick={() =>
                              runGameAction(
                                gameMessage.event.challenge_id!,
                                `/kabul ${gameMessage.event.challenge_id}`,
                              )
                            }
                          >
                            Kabul et
                          </button>
                          <button
                            type="button"
                            className="chance-card__secondary"
                            disabled={gameActionBusy !== null}
                            onClick={() =>
                              runGameAction(
                                gameMessage.event.challenge_id!,
                                `/reddet ${gameMessage.event.challenge_id}`,
                              )
                            }
                          >
                            Reddet
                          </button>
                        </div>
                      ) : gameMessage.event.challenger?.toLocaleLowerCase("tr") === currentUsername ? (
                        <div className="chance-card__actions">
                          <button
                            type="button"
                            className="chance-card__secondary"
                            disabled={gameActionBusy !== null}
                            onClick={() =>
                              runGameAction(
                                gameMessage.event.challenge_id!,
                                `/iptal ${gameMessage.event.challenge_id}`,
                              )
                            }
                          >
                            Daveti iptal et
                          </button>
                        </div>
                      ) : (
                        <span className="chance-card__status">Rakibin yanıtı bekleniyor</span>
                      )
                    ) : null}
                  </div>
                ) : (
                  <span className="chat-message__content">{message.content || "(silindi)"}</span>
                )}
                {message.delivery_status === "sending" ? (
                  <span className="chat-message__delivery">Gönderiliyor…</span>
                ) : message.delivery_status === "failed" && message.client_id ? (
                  <button
                    type="button"
                    className="chat-message__delivery chat-message__retry"
                    onClick={() => onRetryMessage(message.client_id!, message.content)}
                  >
                    Gönderilemedi · Tekrar dene
                  </button>
                ) : null}
                {own && message.content && !message.delivery_status ? (
                  <button
                    className="chat-message__delete"
                    title="Mesajı sil"
                    onClick={() => {
                      if (window.confirm("Bu mesaj silinsin mi?")) onDeleteMessage(message.event_id);
                    }}
                  >
                    🗑️
                  </button>
                ) : null}
              </div>
            );
          })
        )}
      </div>
      {unseenMessageCount > 0 ? (
        <button
          type="button"
          className="chat-area__new-message"
          onClick={() => scrollToLatest()}
          aria-label={`${unseenMessageCount} yeni mesaja git`}
          title={`${unseenMessageCount} yeni mesaj`}
        >
          <span aria-hidden="true">⌄</span>
        </button>
      ) : null}
      {channel ? (
        <form className="chat-area__composer" onSubmit={handleSubmit}>
          <input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            maxLength={20000}
            placeholder={`#${channel.name} kanalına mesaj yaz`}
          />
          <button type="submit" disabled={!draft.trim()}>
            Gönder
          </button>
        </form>
      ) : null}
    </section>
  );
}
