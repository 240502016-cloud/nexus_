import { useState } from "react";
import type { FormEvent } from "react";

import type { Channel, Message } from "../types";

interface ChatAreaProps {
  channel: Channel | undefined;
  messages: Message[];
  currentMatrixUserId: string | null;
  onSendMessage: (content: string) => Promise<void>;
  onDeleteMessage: (eventId: string) => void;
  onRetryMessage: (clientId: string, content: string) => void;
}

function displayName(matrixUserId: string): string {
  // "@aylin:nexus.local" -> "aylin"
  return matrixUserId.replace(/^@/, "").split(":")[0];
}

export function ChatArea({
  channel,
  messages,
  currentMatrixUserId,
  onSendMessage,
  onDeleteMessage,
  onRetryMessage,
}: ChatAreaProps) {
  const [draft, setDraft] = useState("");

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const content = draft.trim();
    if (!content) return;
    // Input'u ağ yanıtını beklemeden temizle; App mesajı aynı anda iyimser olarak listeye ekler.
    setDraft("");
    await onSendMessage(content);
  }

  // API mesajları yeniden eskiye döner; sohbet için eskiden yeniye çeviriyoruz.
  const ordered = [...messages].reverse();

  return (
    <section className="chat-area">
      <header className="chat-area__header">
        {channel ? `${channel.type === "voice" ? "🔊" : "#"} ${channel.name}` : "Bir kanal seçin"}
      </header>
      <div className="chat-area__messages" aria-live="polite">
        {!channel ? null : ordered.length === 0 ? (
          <p className="chat-area__placeholder">Henüz mesaj yok. İlk mesajı sen yaz.</p>
        ) : (
          ordered.map((message) => {
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
                <span className="chat-message__content">{message.content || "(silindi)"}</span>
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
