import { useCallback, useEffect, useRef, useState } from "react";

import { getToken } from "../api/client";
import { webSocketUrl } from "../desktopBridge";
import type { Message } from "../types";

export interface IncomingCall {
  fromUser: number;
  fromUsername: string;
  channelId: number;
  channelName: string;
  serverId: number;
}

export interface OutgoingCall {
  toUser: number;
  toUsername: string;
  channelId: number;
}

export interface CallNotice {
  kind: "rejected" | "unavailable" | "error";
  text: string;
}

export interface PresenceInfo {
  online: boolean;
  status: string; // online | idle | dnd | offline
  custom: string;
}

export interface SelfStatus {
  status: "online" | "idle" | "dnd" | "invisible";
  custom: string;
}

// Kanala GİRMEDEN görülen ses kanalı katılımcısı (backend voice roster'ından).
export interface VoiceRosterMember {
  user_id: number;
  username: string;
  avatar_url: string | null;
  muted: boolean;
  deafened: boolean;
  speaking: boolean;
}

export interface ChannelMessageEvent {
  channelId: number;
  serverId: number;
  message: Message | null;
  deletedEventId: string | null;
  sequence: number;
}

export interface DirectMessageEvent {
  conversationId: number;
  senderId: number;
  message: Message;
  sequence: number;
}

export interface SocialEvent {
  event: string;
  sequence: number;
}

interface GatewayMessage {
  type: string;
  [key: string]: unknown;
}

const RECONNECT_MIN_MS = 1500;
const RECONNECT_MAX_MS = 15000;
const HEARTBEAT_INTERVAL_MS = 20_000;
const HEARTBEAT_TIMEOUT_MS = 45_000;

/**
 * Oturum boyunca açık kalan gateway WebSocket'i: presence + çağrı sinyali.
 * Kanal soketinden bağımsızdır; kullanıcı hiçbir kanalda değilken bile çağrı alabilir.
 */
export function useGateway(enabled: boolean) {
  const [connected, setConnected] = useState(false);
  const [presences, setPresences] = useState<Map<number, PresenceInfo>>(new Map());
  const [selfStatus, setSelfStatus] = useState<SelfStatus>({ status: "online", custom: "" });
  const [channelMessage, setChannelMessage] = useState<ChannelMessageEvent | null>(null);
  const [directMessage, setDirectMessage] = useState<DirectMessageEvent | null>(null);
  const [socialEventSequence, setSocialEventSequence] = useState(0);
  const [socialEvent, setSocialEvent] = useState<SocialEvent | null>(null);
  // channelId -> o ses kanalındaki katılımcılar (kanala girmeden görülür).
  const [voiceStates, setVoiceStates] = useState<Map<number, VoiceRosterMember[]>>(new Map());
  const [incomingCall, setIncomingCall] = useState<IncomingCall | null>(null);
  const [outgoingCall, setOutgoingCall] = useState<OutgoingCall | null>(null);
  const [notice, setNotice] = useState<CallNotice | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<number | null>(null);
  const backoffRef = useRef(RECONNECT_MIN_MS);
  const messageSequenceRef = useRef(0);
  const directMessageSequenceRef = useRef(0);
  const socialEventSequenceRef = useRef(0);
  const outgoingRef = useRef<OutgoingCall | null>(null);
  outgoingRef.current = outgoingCall;

  const send = useCallback((message: Record<string, unknown>) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(message));
    }
  }, []);

  useEffect(() => {
    if (!enabled) return;
    let closedByUs = false;
    let heartbeatTimer: number | null = null;
    let lastServerMessageAt = Date.now();

    function clearReconnectTimer() {
      if (reconnectRef.current !== null) {
        window.clearTimeout(reconnectRef.current);
        reconnectRef.current = null;
      }
    }

    function clearHeartbeatTimer() {
      if (heartbeatTimer !== null) {
        window.clearInterval(heartbeatTimer);
        heartbeatTimer = null;
      }
    }

    function scheduleReconnect() {
      if (closedByUs) return;
      clearReconnectTimer();
      if (!navigator.onLine) return; // "online" olayı geldiğinde reconnectNow devreye girer.
      // Çok sayıda istemci aynı anda geri geldiğinde sunucuya yığılmayı önlemek için küçük jitter.
      const delay = Math.round(backoffRef.current * (0.85 + Math.random() * 0.3));
      backoffRef.current = Math.min(backoffRef.current * 2, RECONNECT_MAX_MS);
      reconnectRef.current = window.setTimeout(connect, delay);
    }

    function connect() {
      if (closedByUs) return;
      const current = wsRef.current;
      if (current && (current.readyState === WebSocket.OPEN || current.readyState === WebSocket.CONNECTING)) {
        return;
      }
      if (!navigator.onLine) {
        return;
      }
      clearReconnectTimer();
      const ws = new WebSocket(`${webSocketUrl("/gateway")}?token=${encodeURIComponent(getToken() ?? "")}`);
      wsRef.current = ws;

      ws.onopen = () => {
        backoffRef.current = RECONNECT_MIN_MS;
        lastServerMessageAt = Date.now();
        setConnected(true);
        clearHeartbeatTimer();
        heartbeatTimer = window.setInterval(() => {
          if (ws.readyState !== WebSocket.OPEN) return;
          if (Date.now() - lastServerMessageAt > HEARTBEAT_TIMEOUT_MS) {
            ws.close();
            return;
          }
          ws.send(JSON.stringify({ type: "ping" }));
        }, HEARTBEAT_INTERVAL_MS);
      };

      ws.onmessage = (event) => {
        lastServerMessageAt = Date.now();
        let data: GatewayMessage;
        try {
          data = JSON.parse(event.data) as GatewayMessage;
        } catch {
          return;
        }
        switch (data.type) {
        case "presence-init": {
          const arr = (data.presences as Array<Record<string, unknown>>) ?? [];
          const map = new Map<number, PresenceInfo>();
          for (const p of arr) {
            map.set(p.user_id as number, {
              online: Boolean(p.online),
              status: (p.status as string) ?? "offline",
              custom: (p.custom as string) ?? "",
            });
          }
          setPresences(map);
          break;
        }
        case "presence": {
          const uid = data.user_id as number;
          setPresences((prev) => {
            const next = new Map(prev);
            next.set(uid, {
              online: Boolean(data.online),
              status: (data.status as string) ?? "offline",
              custom: (data.custom as string) ?? "",
            });
            return next;
          });
          break;
        }
        case "self-status":
          setSelfStatus({
            status: (data.status as SelfStatus["status"]) ?? "online",
            custom: (data.custom as string) ?? "",
          });
          break;
        case "channel-message":
          messageSequenceRef.current += 1;
          setChannelMessage({
            channelId: data.channel_id as number,
            serverId: data.server_id as number,
            message: (data.message as Message | undefined) ?? null,
            deletedEventId: (data.deleted_event_id as string | undefined) ?? null,
            sequence: messageSequenceRef.current,
          });
          break;
        case "direct-message":
          directMessageSequenceRef.current += 1;
          setDirectMessage({
            conversationId: data.conversation_id as number,
            senderId: data.sender_id as number,
            message: data.message as Message,
            sequence: directMessageSequenceRef.current,
          });
          break;
        case "social-event":
          socialEventSequenceRef.current += 1;
          setSocialEventSequence(socialEventSequenceRef.current);
          setSocialEvent({
            event: (data.event as string) ?? "unknown",
            sequence: socialEventSequenceRef.current,
          });
          break;
        case "social-sync":
          socialEventSequenceRef.current += 1;
          setSocialEventSequence(socialEventSequenceRef.current);
          break;
        case "pong":
          break;
        case "voice-channel-state": {
          const channelId = data.channel_id as number;
          const participants = (data.participants as VoiceRosterMember[]) ?? [];
          setVoiceStates((prev) => {
            const next = new Map(prev);
            if (participants.length > 0) next.set(channelId, participants);
            else next.delete(channelId);
            return next;
          });
          break;
        }
        case "incoming-call":
          setIncomingCall({
            fromUser: data.from_user as number,
            fromUsername: data.from_username as string,
            channelId: data.channel_id as number,
            channelName: data.channel_name as string,
            serverId: data.server_id as number,
          });
          break;
        case "call-accepted":
          // Karşı taraf kabul etti; zil göstergesini kaldır (ikisi de kanalda buluşur).
          if (outgoingRef.current && outgoingRef.current.toUser === data.from_user) {
            setOutgoingCall(null);
          }
          break;
        case "call-rejected":
          if (outgoingRef.current && outgoingRef.current.toUser === data.from_user) {
            setNotice({ kind: "rejected", text: `${outgoingRef.current.toUsername} çağrıyı reddetti.` });
            setOutgoingCall(null);
          }
          break;
        case "call-unavailable":
          if (outgoingRef.current) {
            setNotice({ kind: "unavailable", text: `${outgoingRef.current.toUsername} çevrimdışı.` });
            setOutgoingCall(null);
          }
          break;
        case "call-cancelled":
          // Arayan vazgeçti; gelen çağrı modalını kapat.
          setIncomingCall((prev) => (prev && prev.fromUser === data.from_user ? null : prev));
          break;
        case "call-error":
          setNotice({ kind: "error", text: "Çağrı başlatılamadı." });
          setOutgoingCall(null);
          break;
        }
      };

      ws.onclose = (event) => {
        clearHeartbeatTimer();
        if (wsRef.current === ws) wsRef.current = null;
        setConnected(false);
        if (event.code === 4401) return; // token geçersiz; aynı token ile sonsuz reconnect yapma.
        scheduleReconnect();
      };
      ws.onerror = () => {
        ws.close();
      };
    }

    function reconnectNow() {
      if (closedByUs) return;
      clearReconnectTimer();
      backoffRef.current = RECONNECT_MIN_MS;
      connect();
    }

    function handleVisibilityChange() {
      if (!document.hidden && wsRef.current?.readyState !== WebSocket.OPEN) reconnectNow();
    }

    function handleOffline() {
      setConnected(false);
      wsRef.current?.close();
    }

    window.addEventListener("online", reconnectNow);
    window.addEventListener("offline", handleOffline);
    document.addEventListener("visibilitychange", handleVisibilityChange);
    connect();

    return () => {
      closedByUs = true;
      clearReconnectTimer();
      clearHeartbeatTimer();
      window.removeEventListener("online", reconnectNow);
      window.removeEventListener("offline", handleOffline);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      wsRef.current?.close();
      wsRef.current = null;
      setConnected(false);
      setPresences(new Map());
      setVoiceStates(new Map());
      setIncomingCall(null);
      setOutgoingCall(null);
    };
  }, [enabled]);

  const setStatus = useCallback(
    (status: SelfStatus["status"], custom: string) => {
      setSelfStatus({ status, custom });
      send({ type: "set-status", status, custom });
    },
    [send],
  );

  const inviteToCall = useCallback(
    (channelId: number, toUser: number, toUsername: string) => {
      setNotice(null);
      setOutgoingCall({ toUser, toUsername, channelId });
      send({ type: "call-invite", to_user_id: toUser, channel_id: channelId });
    },
    [send],
  );

  const acceptCall = useCallback((): IncomingCall | null => {
    const call = incomingCall;
    if (!call) return null;
    send({ type: "call-accept", to_user_id: call.fromUser, channel_id: call.channelId });
    setIncomingCall(null);
    return call;
  }, [incomingCall, send]);

  const rejectCall = useCallback(() => {
    if (!incomingCall) return;
    send({ type: "call-reject", to_user_id: incomingCall.fromUser, channel_id: incomingCall.channelId });
    setIncomingCall(null);
  }, [incomingCall, send]);

  const cancelCall = useCallback(() => {
    if (!outgoingCall) return;
    send({ type: "call-cancel", to_user_id: outgoingCall.toUser, channel_id: outgoingCall.channelId });
    setOutgoingCall(null);
  }, [outgoingCall, send]);

  const clearNotice = useCallback(() => setNotice(null), []);

  return {
    connected,
    presences,
    selfStatus,
    setStatus,
    channelMessage,
    directMessage,
    socialEvent,
    socialEventSequence,
    voiceStates,
    incomingCall,
    outgoingCall,
    notice,
    inviteToCall,
    acceptCall,
    rejectCall,
    cancelCall,
    clearNotice,
  };
}
