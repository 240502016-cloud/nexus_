import { useEffect, useRef, useState } from "react";
import type { FormEvent, KeyboardEvent, ReactNode } from "react";
import { createPortal } from "react-dom";

import { ApiError, coreApi } from "../api/client";
import type { Channel, Member, Message, PinnedMessages } from "../types";
import { parseAttachmentMessage } from "../messageContent";
import { AttachmentCard } from "./AttachmentCard";
import { Icon } from "./Icon";

const GAME_EVENT_PREFIX = "NEXUS_GAME_EVENT:";
const QUICK_REACTIONS = ["👍", "❤️", "😂", "🎉", "😮"];

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
  currentUserId: number;
  members: Member[];
  onSendMessage: (content: string, file?: File, replyTo?: Message) => Promise<void>;
  onEditMessage: (eventId: string, content: string) => Promise<void>;
  onDeleteMessage: (eventId: string) => void;
  onToggleReaction: (eventId: string, emoji: string) => Promise<void>;
  onRetryMessage: (clientId: string, content: string, replyTo?: Message["reply_to"]) => void;
  hasMoreMessages: boolean;
  loadingOlder: boolean;
  onLoadOlder: () => Promise<void>;
  typingUsers: string[];
  onTypingChange: (typing: boolean) => void;
  pinUpdateSequence: number;
}

function displayName(matrixUserId: string): string {
  // "@aylin:nexus.local" -> "aylin"
  return matrixUserId.replace(/^@/, "").split(":")[0];
}

function renderMessageText(content: string, members: Member[]): ReactNode {
  const knownNames = new Set(
    members.map((member) => member.username.toLocaleLowerCase("tr")),
  );
  return content.split(/(@[A-Za-z0-9_.-]{2,32})/g).map((part, index) => {
    if (!part.startsWith("@")) return part;
    const username = part.slice(1).toLowerCase();
    return knownNames.has(username)
      ? <mark className="message-mention" key={`${part}-${index}`}>{part}</mark>
      : part;
  });
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
  currentUserId,
  members,
  onSendMessage,
  onEditMessage,
  onDeleteMessage,
  onToggleReaction,
  onRetryMessage,
  hasMoreMessages,
  loadingOlder,
  onLoadOlder,
  typingUsers,
  onTypingChange,
  pinUpdateSequence,
}: ChatAreaProps) {
  const [draft, setDraft] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [editing, setEditing] = useState<{ eventId: string; content: string } | null>(null);
  const [replyingTo, setReplyingTo] = useState<Message | null>(null);
  const [gameActionBusy, setGameActionBusy] = useState<string | null>(null);
  const [unseenMessageCount, setUnseenMessageCount] = useState(0);
  const [reactionPickerFor, setReactionPickerFor] = useState<string | null>(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchUserId, setSearchUserId] = useState<number | null>(null);
  const [searchResults, setSearchResults] = useState<Message[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [pinsOpen, setPinsOpen] = useState(false);
  const [aiOpen, setAiOpen] = useState(false);
  const [aiMode, setAiMode] = useState<"summary" | "search">("summary");
  const [aiQuestion, setAiQuestion] = useState("");
  const [aiResult, setAiResult] = useState("");
  const [aiError, setAiError] = useState("");
  const [aiBusy, setAiBusy] = useState(false);
  const [pinnedMessages, setPinnedMessages] = useState<PinnedMessages>({
    items: [],
    can_manage: false,
  });
  const [pinsLoaded, setPinsLoaded] = useState(false);
  const [seenPinnedSignature, setSeenPinnedSignature] = useState("");
  const messagesRef = useRef<HTMLDivElement | null>(null);
  const historyRequestRef = useRef(false);
  const knownMessageIdsRef = useRef<Set<string>>(new Set());
  const initializedChannelRef = useRef<number | null>(null);
  const isNearBottomRef = useRef(true);
  const forceScrollToBottomRef = useRef(false);
  const composerRef = useRef<HTMLTextAreaElement | null>(null);
  const typingStopTimerRef = useRef<number | null>(null);
  const aiOperationRef = useRef(0);
  const onTypingChangeRef = useRef(onTypingChange);
  onTypingChangeRef.current = onTypingChange;

  const pinnedIds = new Set(pinnedMessages.items.map((message) => message.event_id));
  const pinnedSignature = [...pinnedIds].sort().join("|");
  const seenPinnedIds = new Set(seenPinnedSignature ? seenPinnedSignature.split("|") : []);
  const hasUnseenPins =
    pinsLoaded && pinnedMessages.items.some((message) => !seenPinnedIds.has(message.event_id));
  const mentionMatch = draft.match(/(?:^|\s)@([A-Za-z0-9_.-]*)$/);
  const mentionNeedle = mentionMatch?.[1]?.toLocaleLowerCase("tr") ?? "";
  const mentionCandidates = mentionMatch
    ? members
        .filter((member) =>
          member.id !== currentUserId &&
          member.username.toLocaleLowerCase("tr").startsWith(mentionNeedle)
        )
        .slice(0, 6)
    : [];

  function stopTyping() {
    if (typingStopTimerRef.current !== null) {
      window.clearTimeout(typingStopTimerRef.current);
      typingStopTimerRef.current = null;
    }
    onTypingChangeRef.current(false);
  }

  function updateDraft(value: string) {
    setDraft(value);
    if (typingStopTimerRef.current !== null) window.clearTimeout(typingStopTimerRef.current);
    if (!value.trim()) {
      stopTyping();
      return;
    }
    onTypingChangeRef.current(true);
    typingStopTimerRef.current = window.setTimeout(stopTyping, 2_500);
  }

  function completeMention(username: string) {
    setDraft((current) =>
      current.replace(/(^|\s)@[A-Za-z0-9_.-]*$/, `$1@${username} `)
    );
    requestAnimationFrame(() => composerRef.current?.focus());
  }

  function resizeComposer(element = composerRef.current) {
    if (!element) return;
    element.style.height = "auto";
    const style = window.getComputedStyle(element);
    const lineHeight = Number.parseFloat(style.lineHeight) || 22;
    const padding = Number.parseFloat(style.paddingTop) + Number.parseFloat(style.paddingBottom);
    const maxHeight = lineHeight * 8 + padding;
    element.style.height = `${Math.min(element.scrollHeight, maxHeight)}px`;
    element.style.overflowY = element.scrollHeight > maxHeight ? "auto" : "hidden";
  }

  function scrollToLatest(behavior: ScrollBehavior = "smooth") {
    const container = messagesRef.current;
    if (!container) return;
    if (behavior === "smooth") {
      container.scrollTo({ top: container.scrollHeight, behavior });
    } else {
      container.scrollTop = container.scrollHeight;
    }
    isNearBottomRef.current = true;
    setUnseenMessageCount(0);
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const content = draft.trim();
    if (!content && !selectedFile) return;
    // Input'u ağ yanıtını beklemeden temizle; App mesajı aynı anda iyimser olarak listeye ekler.
    setDraft("");
    stopTyping();
    const file = selectedFile ?? undefined;
    setSelectedFile(null);
    requestAnimationFrame(() => resizeComposer());
    forceScrollToBottomRef.current = true;
    const replyTarget = replyingTo ?? undefined;
    setReplyingTo(null);
    const pending = onSendMessage(content, file, replyTarget);
    // İyimser mesajın React tarafından DOM'a işlendiği iki çizim turundan sonra kesin olarak
    // en alta in. Ağ yanıtını beklemek kullanıcının kendi mesajını görmesini geciktirirdi.
    requestAnimationFrame(() => requestAnimationFrame(() => scrollToLatest("auto")));
    await pending;
  }

  async function saveEdit(event: FormEvent) {
    event.preventDefault();
    if (!editing?.content.trim()) return;
    await onEditMessage(editing.eventId, editing.content.trim());
    setEditing(null);
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
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

  function selectReply(message: Message) {
    setReplyingTo(message);
    requestAnimationFrame(() => composerRef.current?.focus());
  }

  function scrollToMessage(eventId: string) {
    const element = document.getElementById(`message-${encodeURIComponent(eventId)}`);
    element?.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  useEffect(() => {
    knownMessageIdsRef.current = new Set();
    initializedChannelRef.current = channel?.id ?? null;
    isNearBottomRef.current = true;
    forceScrollToBottomRef.current = false;
    setReplyingTo(null);
    setReactionPickerFor(null);
    setSearchOpen(false);
    setSearchResults([]);
    setSearchError("");
    setPinsOpen(false);
    setPinsLoaded(false);
    setSeenPinnedSignature("");
    setAiOpen(false);
    setAiQuestion("");
    setAiResult("");
    setAiError("");
    setAiBusy(false);
    aiOperationRef.current += 1;
    setUnseenMessageCount(0);
  }, [channel?.id]);

  useEffect(() => {
    return () => {
      if (typingStopTimerRef.current !== null) {
        window.clearTimeout(typingStopTimerRef.current);
      }
      onTypingChangeRef.current(false);
    };
  }, [channel?.id]);

  useEffect(() => {
    if (!channel) {
      setPinnedMessages({ items: [], can_manage: false });
      setPinsLoaded(false);
      return;
    }
    let cancelled = false;
    coreApi.listPinnedMessages(channel.id)
      .then((result) => {
        if (!cancelled) {
          setPinnedMessages(result);
          setPinsLoaded(true);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setPinnedMessages({ items: [], can_manage: false });
          setPinsLoaded(true);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [channel?.id, pinUpdateSequence]);

  useEffect(() => {
    if (!channel || !pinsLoaded) return;
    const storageKey = `nexus.pins.seen.${currentUserId}.${channel.id}`;
    const stored = localStorage.getItem(storageKey);
    if (stored === null) {
      localStorage.setItem(storageKey, pinnedSignature);
      setSeenPinnedSignature(pinnedSignature);
      return;
    }
    setSeenPinnedSignature(stored);
  }, [channel?.id, currentUserId, pinsLoaded]);

  useEffect(() => {
    if (!channel || !pinsLoaded || !pinsOpen) return;
    const storageKey = `nexus.pins.seen.${currentUserId}.${channel.id}`;
    localStorage.setItem(storageKey, pinnedSignature);
    setSeenPinnedSignature(pinnedSignature);
  }, [channel?.id, currentUserId, pinnedSignature, pinsLoaded, pinsOpen]);

  useEffect(() => resizeComposer(), [draft]);

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

  async function runSearch(event: FormEvent) {
    event.preventDefault();
    if (!channel || searchQuery.trim().length < 2) return;
    setSearching(true);
    setSearchError("");
    try {
      setSearchResults(
        await coreApi.searchMessages(channel.id, searchQuery.trim(), searchUserId),
      );
    } catch (error) {
      setSearchResults([]);
      setSearchError(error instanceof Error ? error.message : "Mesaj araması tamamlanamadı.");
    } finally {
      setSearching(false);
    }
  }

  async function runAiAssistant(event: FormEvent) {
    event.preventDefault();
    if (!channel || messages.length === 0 || (aiMode === "search" && aiQuestion.trim().length < 3)) {
      return;
    }

    const operation = aiOperationRef.current + 1;
    aiOperationRef.current = operation;
    setAiBusy(true);
    setAiError("");
    setAiResult("");

    const transcript = messages
      .filter((message) => !message.hidden && message.content.trim())
      .slice(0, 60)
      .reverse()
      .map((message) => {
        const timestamp = message.origin_server_ts
          ? new Date(message.origin_server_ts).toLocaleString("tr-TR")
          : "";
        return `[${timestamp}] ${displayName(message.sender)}: ${message.content.slice(0, 600)}`;
      })
      .join("\n")
      .slice(-15_000);

    const instruction = aiMode === "summary"
      ? [
          "Aşağıdaki Nexus kanal dökümünü yalnızca verilen bilgilere dayanarak Türkçe özetle.",
          "Önemli kararları, açık işleri ve konuşulan sorunları kısa maddeler halinde ver.",
          "Dökümde olmayan bilgi üretme. Hassas veya kişisel ayrıntıları gereksiz yere tekrar etme.",
        ].join(" ")
      : [
          "Aşağıdaki Nexus kanal dökümünde kullanıcının sorusuyla ilgili konuşmaları bul.",
          "İlgili kişileri, yaklaşık zamanı ve kısa bağlamı Türkçe olarak belirt.",
          "Eşleşme yoksa açıkça bulunamadığını söyle; döküm dışında bilgi üretme.",
          `Kullanıcının sorusu: ${aiQuestion.trim()}`,
        ].join(" ");

    try {
      const conversation = await coreApi.createAiConversation(
        `#${channel.name} ${aiMode === "summary" ? "özeti" : "akıllı arama"}`,
      );
      if (aiOperationRef.current !== operation) return;
      let job = await coreApi.sendAiMessage(
        conversation.id,
        `${instruction}\n\nKANAL DÖKÜMÜ:\n${transcript}`,
        crypto.randomUUID(),
      );

      for (let attempt = 0; attempt < 75; attempt += 1) {
        if (aiOperationRef.current !== operation) return;
        if (job.status === "succeeded") {
          setAiResult(job.output_text?.trim() || "AI yanıtı boş döndü.");
          return;
        }
        if (job.status === "failed" || job.status === "cancelled") {
          throw new Error(job.error || "AI isteği tamamlanamadı.");
        }
        await new Promise((resolve) => window.setTimeout(resolve, 1_200));
        job = await coreApi.getAiJob(job.id);
      }
      throw new Error("AI yanıtı bekleme süresi doldu. İş kuyrukta çalışmaya devam edebilir.");
    } catch (error) {
      if (aiOperationRef.current !== operation) return;
      if (error instanceof ApiError && [502, 503, 504].includes(error.status)) {
        setAiError("AI Gateway şu anda kapalı veya ulaşılamıyor. Nexus’un diğer özellikleri çalışmaya devam ediyor.");
      } else {
        setAiError(error instanceof Error ? error.message : "AI isteği tamamlanamadı.");
      }
    } finally {
      if (aiOperationRef.current === operation) setAiBusy(false);
    }
  }

  async function togglePin(message: Message) {
    if (!channel || !pinnedMessages.can_manage) return;
    if (pinnedIds.has(message.event_id)) {
      await coreApi.unpinMessage(channel.id, message.event_id);
      setPinnedMessages((current) => ({
        ...current,
        items: current.items.filter((item) => item.event_id !== message.event_id),
      }));
    } else {
      await coreApi.pinMessage(channel.id, message.event_id);
      setPinnedMessages((current) => ({
        ...current,
        items: [...current.items, message],
      }));
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
      {channel && document.getElementById("channel-toolbar-portal")
        ? createPortal(
            <div className="chat-area__header-actions">
              <button
                type="button"
                className={searchOpen ? "active" : ""}
                onClick={() => {
                  setSearchOpen((open) => !open);
                  setPinsOpen(false);
                  setAiOpen(false);
                }}
                title="Mesajlarda ara"
                aria-label="Mesajlarda ara"
              >
                <Icon name="search" />
              </button>
              <button
                type="button"
                className={pinsOpen ? "active" : ""}
                onClick={() => {
                  setPinsOpen((open) => !open);
                  setSearchOpen(false);
                  setAiOpen(false);
                }}
                title="Sabit mesajlar"
                aria-label="Sabit mesajlar"
              >
                <Icon name="pin" />
                {hasUnseenPins ? <small aria-label="Yeni sabitlenen mesaj" /> : null}
              </button>
              <button
                type="button"
                className={aiOpen ? "active message-ai-button" : "message-ai-button"}
                onClick={() => {
                  setAiOpen((open) => !open);
                  setSearchOpen(false);
                  setPinsOpen(false);
                }}
                title="AI kanal yardımcısı"
              >
                AI
              </button>
            </div>,
            document.getElementById("channel-toolbar-portal")!,
          )
        : null}
      <header className="chat-area__header">
        <div className="chat-area__title">
          <strong>{channel ? "Chat" : "Bir kanal seçin"}</strong>
        </div>
      </header>
      {channel && searchOpen ? (
        <aside className="message-tool-panel">
          <form className="message-search" onSubmit={runSearch}>
            <input
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              minLength={2}
              maxLength={200}
              placeholder="Bu kanalda kelime ara"
              autoFocus
            />
            <select
              value={searchUserId ?? ""}
              onChange={(event) => setSearchUserId(event.target.value ? Number(event.target.value) : null)}
              aria-label="Kullanıcıya göre filtrele"
            >
              <option value="">Tüm kullanıcılar</option>
              {members.map((member) => (
                <option key={member.id} value={member.id}>{member.username}</option>
              ))}
            </select>
            <button type="submit" disabled={searching || searchQuery.trim().length < 2}>
              {searching ? "Aranıyor…" : "Ara"}
            </button>
          </form>
          <div className="message-tool-panel__results">
            {searchResults.map((message) => (
              <button
                type="button"
                key={message.event_id}
                onClick={() => scrollToMessage(message.event_id)}
              >
                <strong>{displayName(message.sender)}</strong>
                <span>{message.content}</span>
              </button>
            ))}
            {!searching && !searchError && searchQuery.length >= 2 && searchResults.length === 0 ? (
              <p>Sonuç bulunamadı.</p>
            ) : null}
            {searchError ? <p className="message-tool-panel__error">{searchError}</p> : null}
          </div>
        </aside>
      ) : null}
      {channel && pinsOpen ? (
        <aside className="message-tool-panel">
          <div className="message-tool-panel__title">
            <strong>Sabit mesajlar</strong>
            <span>{pinnedMessages.items.length}/50</span>
          </div>
          <div className="message-tool-panel__results">
            {pinnedMessages.items.map((message) => (
              <button
                type="button"
                key={message.event_id}
                onClick={() => scrollToMessage(message.event_id)}
              >
                <strong>{displayName(message.sender)}</strong>
                <span>{message.content}</span>
              </button>
            ))}
            {pinnedMessages.items.length === 0 ? <p>Henüz sabit mesaj yok.</p> : null}
          </div>
        </aside>
      ) : null}
      {channel && aiOpen ? (
        <aside className="message-tool-panel message-ai-panel">
          <form onSubmit={runAiAssistant}>
            <div className="message-tool-panel__title">
              <strong>AI kanal yardımcısı</strong>
              <span>Son {Math.min(messages.length, 60)} mesaj</span>
            </div>
            <div className="message-ai-panel__modes" role="group" aria-label="AI işlemi">
              <button
                type="button"
                className={aiMode === "summary" ? "active" : ""}
                onClick={() => setAiMode("summary")}
              >
                Ben yokken ne oldu?
              </button>
              <button
                type="button"
                className={aiMode === "search" ? "active" : ""}
                onClick={() => setAiMode("search")}
              >
                Akıllı arama
              </button>
            </div>
            {aiMode === "search" ? (
              <input
                value={aiQuestion}
                onChange={(event) => setAiQuestion(event.target.value)}
                minLength={3}
                maxLength={500}
                placeholder="Örn. Geçen konuştuğumuz sunucu sorununu bul"
                autoFocus
              />
            ) : (
              <p>Yüklenen son mesajlar özetlenir; ağır işlem mevcut AI Gateway kuyruğunda çalışır.</p>
            )}
            <button
              type="submit"
              disabled={
                aiBusy ||
                messages.length === 0 ||
                (aiMode === "search" && aiQuestion.trim().length < 3)
              }
            >
              {aiBusy ? "AI düşünüyor…" : aiMode === "summary" ? "Özetle" : "Ara"}
            </button>
          </form>
          {aiError ? <div className="message-ai-panel__error" role="status">{aiError}</div> : null}
          {aiResult ? <div className="message-ai-panel__result">{aiResult}</div> : null}
        </aside>
      ) : null}
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
              <div
                key={message.event_id}
                id={`message-${encodeURIComponent(message.event_id)}`}
                className={className}
              >
                <div className="chat-message__body">
                <div className="chat-message__meta">
                  <span className="chat-message__sender">{displayName(message.sender)}</span>
                  <time
                    dateTime={message.origin_server_ts ? new Date(message.origin_server_ts).toISOString() : undefined}
                    title={message.origin_server_ts ? new Date(message.origin_server_ts).toLocaleString("tr-TR") : "Yeni mesaj"}
                  >
                    {message.origin_server_ts
                      ? new Date(message.origin_server_ts).toLocaleTimeString("tr-TR", {
                          hour: "2-digit",
                          minute: "2-digit",
                        })
                      : "şimdi"}
                  </time>
                </div>
                {message.reply_to ? (
                  <button
                    type="button"
                    className="message-reply-quote"
                    onClick={() => scrollToMessage(message.reply_to!.event_id)}
                    title="Yanıtlanan mesaja git"
                  >
                    <strong>{displayName(message.reply_to.sender)}</strong>
                    <span>{message.reply_to.content || "(silindi)"}</span>
                  </button>
                ) : null}
                {editing?.eventId === message.event_id ? (
                  <form className="chat-message__edit-form" onSubmit={saveEdit}>
                    <textarea
                      autoFocus
                      value={editing.content}
                      onChange={(event) => setEditing({ ...editing, content: event.target.value })}
                      onKeyDown={(event) => {
                        if (event.key === "Escape") setEditing(null);
                        if (event.key === "Enter" && !event.shiftKey) {
                          event.preventDefault();
                          event.currentTarget.form?.requestSubmit();
                        }
                      }}
                    />
                    <span>Enter kaydet · Esc iptal · Shift+Enter yeni satır</span>
                  </form>
                ) : gameMessage ? (
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
                ) : parseAttachmentMessage(message.content) ? (
                  <AttachmentCard {...parseAttachmentMessage(message.content)!} />
                ) : (
                  <span className="chat-message__content">
                    {message.content ? renderMessageText(message.content, members) : "(silindi)"}
                    {message.edited ? <small className="chat-message__edited"> (düzenlendi)</small> : null}
                  </span>
                )}
                {(message.reactions?.length ?? 0) > 0 ? (
                  <div className="message-reactions" aria-label="Mesaj reaksiyonları">
                    {message.reactions!.map((reaction) => (
                      <button
                        type="button"
                        key={reaction.emoji}
                        className={reaction.me ? "message-reaction message-reaction--mine" : "message-reaction"}
                        onClick={() => void onToggleReaction(message.event_id, reaction.emoji)}
                        title={reaction.me ? "Reaksiyonunu kaldır" : "Aynı reaksiyonu ekle"}
                      >
                        <span>{reaction.emoji}</span>
                        <strong>{reaction.count}</strong>
                      </button>
                    ))}
                  </div>
                ) : null}
                {message.delivery_status === "sending" ? (
                  <span className="chat-message__delivery">Gönderiliyor…</span>
                ) : message.delivery_status === "failed" && message.client_id ? (
                  <button
                    type="button"
                    className="chat-message__delivery chat-message__retry"
                    onClick={() => onRetryMessage(message.client_id!, message.content, message.reply_to)}
                  >
                    Gönderilemedi · Tekrar dene
                  </button>
                ) : null}
                {reactionPickerFor === message.event_id ? (
                  <div className="reaction-picker" aria-label="Hızlı reaksiyonlar">
                    {QUICK_REACTIONS.map((emoji) => (
                      <button
                        type="button"
                        key={emoji}
                        onClick={() => {
                          setReactionPickerFor(null);
                          void onToggleReaction(message.event_id, emoji);
                        }}
                      >
                        {emoji}
                      </button>
                    ))}
                  </div>
                ) : null}
                </div>
                {message.content && !message.delivery_status ? (
                  <div className="chat-message__actions">
                    <button
                      type="button"
                      title="Reaksiyon ekle"
                      onClick={() =>
                        setReactionPickerFor((current) =>
                          current === message.event_id ? null : message.event_id
                        )
                      }
                    >
                      <Icon name="smile" />
                    </button>
                    <button
                      type="button"
                      title="Yanıtla"
                      onClick={() => selectReply(message)}
                    >
                      <Icon name="reply" />
                    </button>
                    {own && !gameMessage ? (
                      <button
                        type="button"
                        title="Mesajı düzenle"
                        onClick={() => setEditing({ eventId: message.event_id, content: message.content })}
                      >
                        <Icon name="edit" />
                      </button>
                    ) : null}
                    {own ? (
                      <button
                        type="button"
                        title="Mesajı sil"
                        onClick={() => {
                          if (window.confirm("Bu mesaj silinsin mi?")) onDeleteMessage(message.event_id);
                        }}
                      >
                        <Icon name="trash" />
                      </button>
                    ) : null}
                    {pinnedMessages.can_manage ? (
                      <button
                        type="button"
                        title={pinnedIds.has(message.event_id) ? "Sabitlemeyi kaldır" : "Mesajı sabitle"}
                        onClick={() => void togglePin(message)}
                      >
                        <Icon name="pin" />
                      </button>
                    ) : null}
                  </div>
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
      {channel && typingUsers.length > 0 ? (
        <div className="chat-area__typing" aria-live="polite">
          <span />
          {typingUsers.length === 1
            ? `${typingUsers[0]} yazıyor…`
            : `${typingUsers.slice(0, 2).join(", ")} yazıyor…`}
        </div>
      ) : null}
      {channel ? (
        <form className="chat-area__composer" onSubmit={handleSubmit}>
          {replyingTo ? (
            <div className="composer-reply-preview">
              <Icon name="reply" />
              <div>
                <strong>{displayName(replyingTo.sender)} kullanıcısına yanıt</strong>
                <span>{replyingTo.content || "(silindi)"}</span>
              </div>
              <button type="button" onClick={() => setReplyingTo(null)} aria-label="Yanıtı iptal et">
                <Icon name="close" />
              </button>
            </div>
          ) : null}
          {mentionCandidates.length > 0 ? (
            <div className="mention-suggestions" role="listbox" aria-label="Mention önerileri">
              {mentionCandidates.map((member) => (
                <button
                  type="button"
                  key={member.id}
                  role="option"
                  onClick={() => completeMention(member.username)}
                >
                  <strong>@{member.username}</strong>
                  {member.display_name ? <span>{member.display_name}</span> : null}
                </button>
              ))}
            </div>
          ) : null}
          <input
            id="chat-file-input"
            className="visually-hidden"
            type="file"
            onChange={(event) => setSelectedFile(event.target.files?.[0] ?? null)}
          />
          <label className="composer-icon-button" htmlFor="chat-file-input" title="Fotoğraf veya dosya ekle">
            <Icon name="paperclip" />
          </label>
          {selectedFile ? (
            <span className="chat-area__selected-file">
              {selectedFile.name}
              <button type="button" onClick={() => setSelectedFile(null)} aria-label="Dosyayı kaldır">
                <Icon name="close" />
              </button>
            </span>
          ) : null}
          <textarea
            ref={composerRef}
            rows={1}
            value={draft}
            onChange={(event) => {
              updateDraft(event.target.value);
              resizeComposer(event.target);
            }}
            onKeyDown={handleComposerKeyDown}
            maxLength={20000}
            placeholder={`#${channel.name} kanalına mesaj yaz · Shift+Enter yeni satır`}
          />
          <button type="submit" disabled={!draft.trim() && !selectedFile}>
            <Icon name="send" />
            <span>Gönder</span>
          </button>
        </form>
      ) : null}
    </section>
  );
}
