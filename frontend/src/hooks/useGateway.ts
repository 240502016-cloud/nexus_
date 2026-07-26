import { useCallback, useEffect, useRef, useState } from "react";

import { getToken } from "../api/client";

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

interface GatewayMessage {
  type: string;
  [key: string]: unknown;
}

const RECONNECT_MIN_MS = 1500;
const RECONNECT_MAX_MS = 15000;

/**
 * Oturum boyunca açık kalan gateway WebSocket'i: presence + çağrı sinyali.
 * Kanal soketinden bağımsızdır; kullanıcı hiçbir kanalda değilken bile çağrı alabilir.
 */
export function useGateway(enabled: boolean) {
  const [presences, setPresences] = useState<Map<number, PresenceInfo>>(new Map());
  const [selfStatus, setSelfStatus] = useState<SelfStatus>({ status: "online", custom: "" });
  // Gerçek zamanlı mesaj sinyali: bir kanalda yeni mesaj olduğunda nonce artar.
  const [messageSignal, setMessageSignal] = useState(0);
  const [messageChannelId, setMessageChannelId] = useState<number | null>(null);
  // channelId -> o ses kanalındaki katılımcılar (kanala girmeden görülür).
  const [voiceStates, setVoiceStates] = useState<Map<number, VoiceRosterMember[]>>(new Map());
  const [incomingCall, setIncomingCall] = useState<IncomingCall | null>(null);
  const [outgoingCall, setOutgoingCall] = useState<OutgoingCall | null>(null);
  const [notice, setNotice] = useState<CallNotice | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<number | null>(null);
  const backoffRef = useRef(RECONNECT_MIN_MS);
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

    function scheduleReconnect() {
      if (closedByUs) return;
      const delay = backoffRef.current;
      backoffRef.current = Math.min(backoffRef.current * 2, RECONNECT_MAX_MS);
      reconnectRef.current = window.setTimeout(connect, delay);
    }

    function connect() {
      const protocol = window.location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${protocol}://${window.location.host}/api/gateway?token=${getToken() ?? ""}`);
      wsRef.current = ws;

      ws.onopen = () => {
        backoffRef.current = RECONNECT_MIN_MS;
      };

      ws.onmessage = (event) => {
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
          setMessageChannelId(data.channel_id as number);
          setMessageSignal((n) => n + 1);
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

      ws.onclose = () => {
        wsRef.current = null;
        scheduleReconnect();
      };
      ws.onerror = () => {
        ws.close();
      };
    }

    connect();

    return () => {
      closedByUs = true;
      if (reconnectRef.current) window.clearTimeout(reconnectRef.current);
      wsRef.current?.close();
      wsRef.current = null;
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
    presences,
    selfStatus,
    setStatus,
    messageSignal,
    messageChannelId,
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
