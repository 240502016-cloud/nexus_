import { useEffect, useRef, useState } from "react";
import type { FormEvent, KeyboardEvent } from "react";

import { ApiError, coreApi } from "../api/client";
import type { DirectMessageEvent, PresenceInfo } from "../hooks/useGateway";
import type {
  DirectConversation,
  Friend,
  FriendRequestList,
  Message,
  PublicUser,
  User,
} from "../types";

type ProfileTab = "profile" | "friends" | "messages";

interface ProfilePanelProps {
  currentUser: User;
  presences: Map<number, PresenceInfo>;
  directMessage: DirectMessageEvent | null;
  socialEventSequence: number;
  onClose: () => void;
  onOpenSettings: () => void;
}

function initial(name: string): string {
  return name.trim().charAt(0).toUpperCase() || "?";
}

function clientId(): string {
  return typeof crypto.randomUUID === "function"
    ? crypto.randomUUID()
    : `${Date.now()}_${Math.random().toString(36).slice(2)}`;
}

function mergeMessage(current: Message[], incoming: Message): Message[] {
  return [
    incoming,
    ...current.filter(
      (item) =>
        item.event_id !== incoming.event_id &&
        (!incoming.client_id || item.client_id !== incoming.client_id),
    ),
  ];
}

export function ProfilePanel({
  currentUser,
  presences,
  directMessage,
  socialEventSequence,
  onClose,
  onOpenSettings,
}: ProfilePanelProps) {
  const [tab, setTab] = useState<ProfileTab>("profile");
  const [friends, setFriends] = useState<Friend[]>([]);
  const [requests, setRequests] = useState<FriendRequestList>({ incoming: [], outgoing: [] });
  const [conversations, setConversations] = useState<DirectConversation[]>([]);
  const [selectedConversationId, setSelectedConversationId] = useState<number | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [messageCursor, setMessageCursor] = useState<string | null>(null);
  const [hasMoreMessages, setHasMoreMessages] = useState(false);
  const [draft, setDraft] = useState("");
  const [search, setSearch] = useState("");
  const [searchResults, setSearchResults] = useState<PublicUser[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const dmMessagesRef = useRef<HTMLDivElement | null>(null);

  function loadSocial() {
    Promise.all([
      coreApi.listFriends(),
      coreApi.listFriendRequests(),
      coreApi.listDirectConversations(),
    ])
      .then(([friendList, requestList, conversationList]) => {
        setFriends(friendList);
        setRequests(requestList);
        setConversations(conversationList);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Sosyal bilgiler yüklenemedi"));
  }

  useEffect(loadSocial, [socialEventSequence]);

  useEffect(() => {
    const query = search.trim();
    if (query.length < 2) {
      setSearchResults([]);
      return;
    }
    const timer = window.setTimeout(() => {
      coreApi.searchUsers(query).then(setSearchResults).catch(() => setSearchResults([]));
    }, 250);
    return () => window.clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    if (!selectedConversationId) {
      setMessages([]);
      return;
    }
    let cancelled = false;
    coreApi
      .listDirectMessages(selectedConversationId)
      .then((page) => {
        if (cancelled) return;
        setMessages(page.items);
        setMessageCursor(page.next_cursor);
        setHasMoreMessages(page.has_more);
        requestAnimationFrame(() => {
          const container = dmMessagesRef.current;
          if (container) container.scrollTop = container.scrollHeight;
        });
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Özel mesajlar yüklenemedi");
      });
    return () => {
      cancelled = true;
    };
  }, [selectedConversationId]);

  useEffect(() => {
    if (!directMessage || directMessage.conversationId !== selectedConversationId) return;
    setMessages((current) => mergeMessage(current, directMessage.message));
    requestAnimationFrame(() => {
      const container = dmMessagesRef.current;
      if (container) container.scrollTop = container.scrollHeight;
    });
  }, [directMessage?.sequence, selectedConversationId]);

  const selectedConversation = conversations.find(
    (conversation) => conversation.id === selectedConversationId,
  );

  async function sendRequest(username: string) {
    setBusy(`request:${username}`);
    setError(null);
    setNotice(null);
    try {
      await coreApi.sendFriendRequest(username);
      setNotice(`${username} kullanıcısına arkadaşlık isteği gönderildi.`);
      setSearch("");
      setSearchResults([]);
      loadSocial();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Arkadaşlık isteği gönderilemedi");
    } finally {
      setBusy(null);
    }
  }

  async function acceptRequest(friendshipId: number) {
    setBusy(`accept:${friendshipId}`);
    try {
      await coreApi.acceptFriendRequest(friendshipId);
      loadSocial();
    } catch (err) {
      setError(err instanceof Error ? err.message : "İstek kabul edilemedi");
    } finally {
      setBusy(null);
    }
  }

  async function removeFriendship(friendshipId: number, message: string) {
    if (!window.confirm(message)) return;
    setBusy(`remove:${friendshipId}`);
    try {
      await coreApi.removeFriendship(friendshipId);
      if (selectedConversationId === friendshipId) setSelectedConversationId(null);
      loadSocial();
    } catch (err) {
      setError(err instanceof Error ? err.message : "İşlem tamamlanamadı");
    } finally {
      setBusy(null);
    }
  }

  function openConversation(friendshipId: number) {
    setTab("messages");
    setSelectedConversationId(friendshipId);
  }

  async function loadOlderDirectMessages() {
    if (!selectedConversationId || !messageCursor || busy === "older") return;
    setBusy("older");
    const container = dmMessagesRef.current;
    const previousHeight = container?.scrollHeight ?? 0;
    try {
      const page = await coreApi.listDirectMessages(selectedConversationId, 50, messageCursor);
      setMessages((current) => {
        const known = new Set(current.map((item) => item.event_id));
        return [...current, ...page.items.filter((item) => !known.has(item.event_id))];
      });
      setMessageCursor(page.next_cursor);
      setHasMoreMessages(page.has_more);
      requestAnimationFrame(() => {
        if (container) container.scrollTop += container.scrollHeight - previousHeight;
      });
    } finally {
      setBusy(null);
    }
  }

  async function sendDirect(event?: FormEvent) {
    event?.preventDefault();
    if (!selectedConversationId) return;
    const content = draft.trim();
    if (!content) return;
    const id = clientId();
    const optimistic: Message = {
      event_id: `pending-${id}`,
      sender: currentUser.matrix_user_id ?? `@${currentUser.username}:nexus`,
      content,
      origin_server_ts: Date.now(),
      client_id: id,
      delivery_status: "sending",
    };
    setDraft("");
    setMessages((current) => mergeMessage(current, optimistic));
    requestAnimationFrame(() => {
      const container = dmMessagesRef.current;
      if (container) container.scrollTop = container.scrollHeight;
    });
    try {
      const sent = await coreApi.sendDirectMessage(selectedConversationId, content, id);
      setMessages((current) => mergeMessage(current, sent));
    } catch (err) {
      setMessages((current) =>
        current.map((item) =>
          item.client_id === id ? { ...item, delivery_status: "failed" } : item,
        ),
      );
      setError(err instanceof Error ? err.message : "Özel mesaj gönderilemedi");
    }
  }

  function handleDirectKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void sendDirect();
    }
  }

  return (
    <div className="profile-overlay" onClick={onClose}>
      <section className="profile-panel" onClick={(event) => event.stopPropagation()}>
        <header className="profile-panel__header">
          <div>
            <span>NEXUS KİMLİĞİ</span>
            <h2>Profil ve arkadaşlar</h2>
          </div>
          <button type="button" onClick={onClose} aria-label="Profil ekranını kapat">×</button>
        </header>

        <nav className="profile-panel__tabs" aria-label="Profil bölümleri">
          <button className={tab === "profile" ? "active" : ""} onClick={() => setTab("profile")}>
            Profilim
          </button>
          <button className={tab === "friends" ? "active" : ""} onClick={() => setTab("friends")}>
            Arkadaşlar
            {requests.incoming.length ? <b>{requests.incoming.length}</b> : null}
          </button>
          <button className={tab === "messages" ? "active" : ""} onClick={() => setTab("messages")}>
            Özel mesajlar
          </button>
        </nav>

        {error ? <div className="profile-panel__alert profile-panel__alert--error">{error}</div> : null}
        {notice ? <div className="profile-panel__alert">{notice}</div> : null}

        <div className="profile-panel__content">
          {tab === "profile" ? (
            <div className="profile-summary">
              <div className="profile-summary__hero">
                {currentUser.avatar_url ? (
                  <img src={currentUser.avatar_url} alt="" />
                ) : (
                  <span>{initial(currentUser.display_name || currentUser.username)}</span>
                )}
                <div>
                  <span>AKTİF PROFİL</span>
                  <h3>{currentUser.display_name || currentUser.username}</h3>
                  <p>@{currentUser.username}</p>
                </div>
              </div>
              <dl className="profile-summary__details">
                <div><dt>E-posta</dt><dd>{currentUser.email}</dd></div>
                <div><dt>Arkadaşlar</dt><dd>{friends.length}</dd></div>
                <div>
                  <dt>Katılım</dt>
                  <dd>{new Date(currentUser.created_at).toLocaleDateString("tr-TR")}</dd>
                </div>
              </dl>
              <button
                type="button"
                className="profile-panel__primary"
                onClick={() => {
                  onClose();
                  onOpenSettings();
                }}
              >
                Hesap bilgilerini düzenle
              </button>
            </div>
          ) : null}

          {tab === "friends" ? (
            <div className="friends-view">
              <section className="friends-view__search">
                <label htmlFor="friend-search">Kullanıcı ara ve arkadaşlık isteği gönder</label>
                <input
                  id="friend-search"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="En az 2 harf yazın"
                />
                {searchResults.length ? (
                  <ul>
                    {searchResults.map((result) => (
                      <li key={result.id}>
                        <span>{result.display_name || result.username}<small>@{result.username}</small></span>
                        <button
                          type="button"
                          disabled={busy !== null}
                          onClick={() => void sendRequest(result.username)}
                        >
                          {busy === `request:${result.username}` ? "Gönderiliyor…" : "Arkadaş ekle"}
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </section>

              {requests.incoming.length ? (
                <section className="friends-view__section">
                  <h3>Gelen istekler</h3>
                  {requests.incoming.map((request) => (
                    <div className="friend-row" key={request.id}>
                      <span>{request.user.display_name || request.user.username}<small>@{request.user.username}</small></span>
                      <button onClick={() => void acceptRequest(request.id)}>Kabul et</button>
                      <button
                        className="friend-row__danger"
                        onClick={() => void removeFriendship(request.id, "İstek reddedilsin mi?")}
                      >
                        Reddet
                      </button>
                    </div>
                  ))}
                </section>
              ) : null}

              {requests.outgoing.length ? (
                <section className="friends-view__section">
                  <h3>Gönderilen istekler</h3>
                  {requests.outgoing.map((request) => (
                    <div className="friend-row" key={request.id}>
                      <span>{request.user.display_name || request.user.username}<small>Yanıt bekleniyor</small></span>
                      <button
                        className="friend-row__danger"
                        onClick={() => void removeFriendship(request.id, "İstek iptal edilsin mi?")}
                      >
                        İptal
                      </button>
                    </div>
                  ))}
                </section>
              ) : null}

              <section className="friends-view__section">
                <h3>Arkadaşlar · {friends.length}</h3>
                {friends.length ? friends.map((friend) => {
                  const presence = presences.get(friend.user.id);
                  return (
                    <div className="friend-row" key={friend.friendship_id}>
                      <span className={`presence-dot presence-dot--${presence?.status ?? "offline"}`} />
                      <span>
                        {friend.user.display_name || friend.user.username}
                        <small>{presence?.online ? presence.custom || "Çevrimiçi" : "Çevrimdışı"}</small>
                      </span>
                      <button onClick={() => openConversation(friend.friendship_id)}>Mesaj</button>
                      <button
                        className="friend-row__danger"
                        onClick={() =>
                          void removeFriendship(friend.friendship_id, "Bu kişi arkadaşlıktan çıkarılsın mı?")
                        }
                      >
                        Çıkar
                      </button>
                    </div>
                  );
                }) : <p className="profile-panel__empty">Henüz arkadaşınız yok.</p>}
              </section>
            </div>
          ) : null}

          {tab === "messages" ? (
            <div className="direct-view">
              <aside className="direct-view__people">
                <h3>Özel konuşmalar</h3>
                {conversations.map((conversation) => (
                  <button
                    key={conversation.id}
                    className={selectedConversationId === conversation.id ? "active" : ""}
                    onClick={() => setSelectedConversationId(conversation.id)}
                  >
                    <span>{initial(conversation.friend.display_name || conversation.friend.username)}</span>
                    <div>
                      <strong>{conversation.friend.display_name || conversation.friend.username}</strong>
                      <small>@{conversation.friend.username}</small>
                    </div>
                  </button>
                ))}
              </aside>
              <section className="direct-chat">
                {selectedConversation ? (
                  <>
                    <header>
                      <strong>{selectedConversation.friend.display_name || selectedConversation.friend.username}</strong>
                      <span>Özel ve kalıcı konuşma</span>
                    </header>
                    <div className="direct-chat__messages" ref={dmMessagesRef}>
                      {hasMoreMessages ? (
                        <button onClick={() => void loadOlderDirectMessages()} disabled={busy === "older"}>
                          {busy === "older" ? "Yükleniyor…" : "Daha eski mesajlar"}
                        </button>
                      ) : null}
                      {[...messages].reverse().map((message) => {
                        const own =
                          message.sender === currentUser.matrix_user_id ||
                          Boolean(message.delivery_status);
                        return (
                          <div
                            key={message.event_id}
                            className={own ? "direct-message direct-message--own" : "direct-message"}
                          >
                            <small>{own ? "Sen" : selectedConversation.friend.username}</small>
                            <span>{message.content}</span>
                            {message.delivery_status ? <em>{message.delivery_status === "sending" ? "Gönderiliyor…" : "Gönderilemedi"}</em> : null}
                          </div>
                        );
                      })}
                    </div>
                    <form className="direct-chat__composer" onSubmit={sendDirect}>
                      <textarea
                        rows={2}
                        value={draft}
                        onChange={(event) => setDraft(event.target.value)}
                        onKeyDown={handleDirectKeyDown}
                        placeholder="Mesaj yaz · Shift+Enter yeni satır"
                      />
                      <button type="submit" disabled={!draft.trim()}>Gönder</button>
                    </form>
                  </>
                ) : (
                  <div className="direct-chat__empty">
                    <strong>Bir arkadaş seçin</strong>
                    <span>Özel konuşmalar yalnızca iki katılımcı tarafından görülebilir.</span>
                  </div>
                )}
              </section>
            </div>
          ) : null}
        </div>
      </section>
    </div>
  );
}
