import { useCallback, useEffect, useRef, useState } from "react";

import { getToken } from "../api/client";
import type { VoiceSettings } from "../settings";
import { usePushToTalk } from "./usePushToTalk";

export interface VoiceParticipant {
  user_id: number;
  username: string;
  muted: boolean;
  speaking: boolean;
}

interface SignalMessage {
  type: string;
  [key: string]: unknown;
}

const ICE_SERVERS: RTCIceServer[] = [{ urls: "stun:stun.l.google.com:19302" }];
const SPEAKING_THRESHOLD = 12;

export function useVoiceChannel(channelId: number | null, voiceSettings: VoiceSettings) {
  const [connected, setConnected] = useState(false);
  const [participants, setParticipants] = useState<VoiceParticipant[]>([]);
  const [muted, setMuted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const localStreamRef = useRef<MediaStream | null>(null);
  const peersRef = useRef<Map<number, RTCPeerConnection>>(new Map());
  const audioElsRef = useRef<Map<number, HTMLAudioElement>>(new Map());
  const mutedRef = useRef(false);
  // connect() effect'i sadece channelId'ye bağlı çalışır; bağlantı anındaki modu okumak için ref kullanılır.
  const voiceSettingsRef = useRef(voiceSettings);
  voiceSettingsRef.current = voiceSettings;

  const applyMuted = useCallback((nextMuted: boolean) => {
    setMuted(nextMuted);
    mutedRef.current = nextMuted;
    localStreamRef.current?.getAudioTracks().forEach((track) => {
      track.enabled = !nextMuted;
    });
    wsRef.current?.send(JSON.stringify({ type: "mute", muted: nextMuted }));
  }, []);

  const cleanup = useCallback(() => {
    wsRef.current?.close();
    wsRef.current = null;
    peersRef.current.forEach((pc) => pc.close());
    peersRef.current.clear();
    audioElsRef.current.forEach((el) => {
      el.srcObject = null;
    });
    audioElsRef.current.clear();
    localStreamRef.current?.getTracks().forEach((track) => track.stop());
    localStreamRef.current = null;
    setConnected(false);
    setParticipants([]);
    setMuted(false);
    mutedRef.current = false;
  }, []);

  useEffect(() => {
    if (!channelId) {
      cleanup();
      return;
    }

    let cancelled = false;

    function createPeerConnection(peerId: number, ws: WebSocket): RTCPeerConnection {
      const pc = new RTCPeerConnection({ iceServers: ICE_SERVERS });
      if (localStreamRef.current) {
        localStreamRef.current.getTracks().forEach((track) => {
          pc.addTrack(track, localStreamRef.current!);
        });
      } else {
        // Mikrofon yok/reddedildi: yine de "recvonly" bir audio transceiver eklemezsek offer'da
        // hiç audio m-line olmaz ve karşı taraf (ör. müzik botu) bize ses gönderemez - sadece
        // dinleyici olarak katılmak bile mümkün olmaz.
        pc.addTransceiver("audio", { direction: "recvonly" });
      }

      pc.onicecandidate = (event) => {
        if (event.candidate) {
          ws.send(JSON.stringify({ type: "ice-candidate", to: peerId, candidate: event.candidate }));
        }
      };

      pc.ontrack = (event) => {
        let audioEl = audioElsRef.current.get(peerId);
        if (!audioEl) {
          audioEl = new Audio();
          audioEl.autoplay = true;
          audioElsRef.current.set(peerId, audioEl);
        }
        audioEl.srcObject = event.streams[0] ?? null;
      };

      peersRef.current.set(peerId, pc);
      return pc;
    }

    async function connect() {
      setError(null);
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop());
          return;
        }
        localStreamRef.current = stream;
        // Push-to-talk modunda mikrofon varsayılan olarak kapalı başlar, sadece tuş basılıyken açılır.
        if (voiceSettingsRef.current.mode === "ptt") {
          stream.getAudioTracks().forEach((track) => {
            track.enabled = false;
          });
          setMuted(true);
          mutedRef.current = true;
        }
      } catch (err) {
        // Mikrofon olmadan da kanala katılıp diğerlerini (ör. müzik botunu) dinlemeye devam ederiz -
        // sadece kendi sesimizi gönderemeyiz. Önceden burada erken return vardı, bu da mikrofon
        // reddedilince/olmayınca sesli kanala hiç katılamamaya yol açıyordu.
        setError(
          `Mikrofona erişilemedi: ${err instanceof Error ? err.message : String(err)} (sadece dinleyici olarak katılıyorsunuz)`,
        );
      }

      const protocol = window.location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(
        `${protocol}://${window.location.host}/api/channels/${channelId}/voice?token=${getToken() ?? ""}`,
      );
      wsRef.current = ws;

      ws.onmessage = async (event) => {
        const data = JSON.parse(event.data) as SignalMessage;

        switch (data.type) {
          case "peers": {
            const peers = (data.peers as Omit<VoiceParticipant, "speaking">[]).map((p) => ({
              ...p,
              speaking: false,
            }));
            setParticipants(peers);
            setConnected(true);
            // Yeni gelen taraf olarak mesh'i kurma sorumluluğu bizde: mevcut herkese offer gönder.
            for (const peer of peers) {
              const pc = createPeerConnection(peer.user_id, ws);
              const offer = await pc.createOffer();
              await pc.setLocalDescription(offer);
              ws.send(JSON.stringify({ type: "offer", to: peer.user_id, sdp: offer.sdp }));
            }
            break;
          }
          case "peer-joined":
            setParticipants((prev) => [
              ...prev,
              {
                user_id: data.user_id as number,
                username: data.username as string,
                muted: data.muted as boolean,
                speaking: false,
              },
            ]);
            break;
          case "peer-left": {
            const peerId = data.user_id as number;
            peersRef.current.get(peerId)?.close();
            peersRef.current.delete(peerId);
            audioElsRef.current.get(peerId)?.remove();
            audioElsRef.current.delete(peerId);
            setParticipants((prev) => prev.filter((p) => p.user_id !== peerId));
            break;
          }
          case "offer": {
            const fromId = data.from as number;
            const pc = createPeerConnection(fromId, ws);
            await pc.setRemoteDescription({ type: "offer", sdp: data.sdp as string });
            const answer = await pc.createAnswer();
            await pc.setLocalDescription(answer);
            ws.send(JSON.stringify({ type: "answer", to: fromId, sdp: answer.sdp }));
            break;
          }
          case "answer": {
            const pc = peersRef.current.get(data.from as number);
            await pc?.setRemoteDescription({ type: "answer", sdp: data.sdp as string });
            break;
          }
          case "ice-candidate": {
            const pc = peersRef.current.get(data.from as number);
            if (pc && data.candidate) {
              await pc.addIceCandidate(data.candidate as RTCIceCandidateInit);
            }
            break;
          }
          case "mute-changed":
            setParticipants((prev) =>
              prev.map((p) => (p.user_id === data.user_id ? { ...p, muted: data.muted as boolean } : p)),
            );
            break;
          case "speaking-changed":
            setParticipants((prev) =>
              prev.map((p) => (p.user_id === data.user_id ? { ...p, speaking: data.speaking as boolean } : p)),
            );
            break;
        }
      };

      ws.onerror = () => setError("Sesli kanal bağlantı hatası");
      ws.onclose = () => setConnected(false);
    }

    connect();

    return () => {
      cancelled = true;
      cleanup();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [channelId]);

  // Konuşma tespiti: yerel mikrofon seviyesini izler, eşiği geçince "speaking" bildirir.
  useEffect(() => {
    if (!connected || !localStreamRef.current) return;

    const audioContext = new AudioContext();
    const source = audioContext.createMediaStreamSource(localStreamRef.current);
    const analyser = audioContext.createAnalyser();
    analyser.fftSize = 512;
    source.connect(analyser);
    const buffer = new Uint8Array(analyser.frequencyBinCount);

    let lastSpeaking = false;
    let rafId: number;

    function tick() {
      analyser.getByteFrequencyData(buffer);
      const average = buffer.reduce((sum, value) => sum + value, 0) / buffer.length;
      const speaking = average > SPEAKING_THRESHOLD && !mutedRef.current;
      if (speaking !== lastSpeaking) {
        lastSpeaking = speaking;
        wsRef.current?.send(JSON.stringify({ type: "speaking", speaking }));
      }
      rafId = requestAnimationFrame(tick);
    }
    tick();

    return () => {
      cancelAnimationFrame(rafId);
      source.disconnect();
      void audioContext.close();
    };
  }, [connected]);

  const toggleMute = useCallback(() => {
    applyMuted(!mutedRef.current);
  }, [applyMuted]);

  const handlePttChange = useCallback(
    (active: boolean) => {
      applyMuted(!active);
    },
    [applyMuted],
  );
  usePushToTalk(connected && voiceSettings.mode === "ptt", voiceSettings.pttCombo, handlePttChange);

  return { connected, participants, muted, error, toggleMute, disconnect: cleanup };
}
