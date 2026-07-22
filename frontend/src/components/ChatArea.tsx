import { useState } from "react";
import type { FormEvent } from "react";

import type { Channel, Message } from "../types";

interface ChatAreaProps {
  channel: Channel | undefined;
  messages: Message[];
  currentMatrixUserId: string | null;
  onSendMessage: (content: string) => Promise<void>;
}

function displayName(matrixUserId: string): string {
  // "@aylin:nexus.local" -> "aylin"
  return matrixUserId.replace(/^@/, "").split(":")[0];
}

export function ChatArea({ channel, messages, currentMatrixUserId, onSendMessage }: ChatAreaProps) {
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!draft.trim() || sending) return;
    setSending(true);
    try {
      await onSendMessage(draft.trim());
      setDraft("");
    } finally {
      setSending(false);
    }
  }

  // API mesajları yeniden eskiye döner; sohbet için eskiden yeniye çeviriyoruz.
  const ordered = [...messages].reverse();

  return (
    <section className="chat-area">
      <header className="chat-area__header">
        {channel ? `${channel.type === "voice" ? "🔊" : "#"} ${channel.name}` : "Bir kanal seçin"}
      </header>
      <div className="chat-area__messages">
        {!channel ? null : ordered.length === 0 ? (
          <p className="chat-area__placeholder">Henüz mesaj yok. İlk mesajı sen yaz.</p>
        ) : (
          ordered.map((message) => (
            <div
              key={message.event_id}
              className={
                message.sender === currentMatrixUserId ? "chat-message chat-message--own" : "chat-message"
              }
            >
              <span className="chat-message__sender">{displayName(message.sender)}</span>
              <span className="chat-message__content">{message.content || "(silindi)"}</span>
            </div>
          ))
        )}
      </div>
      {channel ? (
        <form className="chat-area__composer" onSubmit={handleSubmit}>
          <input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder={`#${channel.name} kanalına mesaj yaz`}
          />
          <button type="submit" disabled={sending || !draft.trim()}>
            Gönder
          </button>
        </form>
      ) : null}
    </section>
  );
}
