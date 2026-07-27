import { useCallback, useEffect, useRef, useState } from "react";

import { coreApi, getToken } from "../api/client";
import { VIDEO_QUALITY_PRESETS } from "../settings";
import type { VoiceSettings } from "../settings";
import { usePushToTalk } from "./usePushToTalk";

// Seçili mikrofon + ses işleme tercihlerini standart MediaTrackConstraints'e çevirir.
function buildAudioConstraints(vs: VoiceSettings): MediaTrackConstraints {
  const c: MediaTrackConstraints = {
    noiseSuppression: vs.noiseSuppression,
    echoCancellation: vs.echoCancellation,
    autoGainControl: vs.autoGainControl,
  };
  if (vs.inputDeviceId) c.deviceId = { exact: vs.inputDeviceId };
  return c;
}

// Çıkış cihazını (hoparlör) bir media elemanına uygular; desteklenmeyen tarayıcıda sessizce geçer.
async function applySinkId(el: HTMLMediaElement, deviceId: string | null): Promise<void> {
  const withSink = el as HTMLMediaElement & { setSinkId?: (id: string) => Promise<void> };
  if (typeof withSink.setSinkId !== "function") return;
  try {
    await withSink.setSinkId(deviceId ?? "");
  } catch {
    /* cihaz yok / izin yok - yok say */
  }
}

export interface VoiceParticipant {
  user_id: number;
  username: string;
  muted: boolean;
  deafened: boolean;
  speaking: boolean;
}

export type VideoKind = "camera" | "screen" | null;

interface SignalMessage {
  type: string;
  [key: string]: unknown;
}

// Her peer için "perfect negotiation" (MDN) durumunu tutar. Böylece bağlantı kurulduktan
// SONRA da (ekran paylaşımı/kamera açılınca) track eklenip yeniden pazarlık yapılabilir.
interface PeerState {
  pc: RTCPeerConnection;
  makingOffer: boolean;
  ignoreOffer: boolean;
  polite: boolean;
  videoSender: RTCRtpSender;
  videoTransceiver: RTCRtpTransceiver;
}

const SPEAKING_THRESHOLD = 12;

function buildCameraConstraints(vs: VoiceSettings, deviceId: string | null): MediaTrackConstraints {
  const preset = VIDEO_QUALITY_PRESETS[vs.videoQuality];
  return {
    ...(deviceId ? { deviceId: { exact: deviceId } } : {}),
    width: { ideal: preset.width, max: preset.width },
    height: { ideal: preset.height, max: preset.height },
    frameRate: { ideal: vs.videoFrameRate, max: vs.videoFrameRate },
    aspectRatio: { ideal: 16 / 9 },
  };
}

function buildScreenConstraints(vs: VoiceSettings): MediaTrackConstraints {
  const preset = VIDEO_QUALITY_PRESETS[vs.videoQuality];
  return {
    width: { ideal: preset.width, max: preset.width },
    height: { ideal: preset.height, max: preset.height },
    frameRate: { ideal: vs.videoFrameRate, max: vs.videoFrameRate },
  };
}

async function optimizeVideoSender(
  sender: RTCRtpSender,
  kind: Exclude<VideoKind, null>,
  vs: VoiceSettings,
): Promise<void> {
  try {
    const preset = VIDEO_QUALITY_PRESETS[vs.videoQuality];
    const baseBitrate = kind === "screen" ? preset.screenBitrate : preset.cameraBitrate;
    const frameRateMultiplier = vs.videoFrameRate === 60 ? 1.25 : 1;
    const parameters = sender.getParameters();
    if (!parameters.encodings?.length) parameters.encodings = [{}];
    parameters.encodings[0].maxBitrate = Math.round(baseBitrate * frameRateMultiplier);
    parameters.encodings[0].maxFramerate = vs.videoFrameRate;
    parameters.degradationPreference = "maintain-resolution";
    await sender.setParameters(parameters);
  } catch {
    // Bazı tarayıcılar kodlayıcı parametrelerinin bir kısmını desteklemez; varsayılan uyarlama sürer.
  }
}

export function useVoiceChannel(channelId: number | null, voiceSettings: VoiceSettings) {
  const [connected, setConnected] = useState(false);
  const [participants, setParticipants] = useState<VoiceParticipant[]>([]);
  const [muted, setMuted] = useState(false);
  const [deafened, setDeafened] = useState(false);
  const [videoKind, setVideoKind] = useState<VideoKind>(null);
  const [localVideoStream, setLocalVideoStream] = useState<MediaStream | null>(null);
  // user_id -> uzak medya akışı (ses + varsa video). VideoStage bunları render eder.
  const [remoteStreams, setRemoteStreams] = useState<Map<number, MediaStream>>(new Map());
  const [ignoredRemoteVideoIds, setIgnoredRemoteVideoIds] = useState<Set<number>>(new Set());
  const [error, setError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const localStreamRef = useRef<MediaStream | null>(null); // mikrofon (audio)
  const videoTrackRef = useRef<MediaStreamTrack | null>(null); // yerel kamera/ekran track'i
  const videoKindRef = useRef<VideoKind>(null);
  const peersRef = useRef<Map<number, PeerState>>(new Map());
  const pendingIceRef = useRef<Map<number, RTCIceCandidateInit[]>>(new Map());
  const audioElsRef = useRef<Map<number, HTMLAudioElement>>(new Map());
  // Her peer için tek bir birleşik uzak MediaStream. Ses ve video ayrı MSID'lerle gelse de
  // aynı stream'de biriktirilir; böylece video eklenince ses stream'i ezilmez (Hata 1).
  const remoteMediaRef = useRef<Map<number, MediaStream>>(new Map());
  const ignoredRemoteVideoIdsRef = useRef<Set<number>>(new Set());
  const mutedRef = useRef(false);
  const deafenedRef = useRef(false);
  const preDeafenMutedRef = useRef(false); // deafen açılmadan önceki mute durumu
  // Video kontrol fonksiyonları connect effect'i içinde tanımlanır; dışarıya sabit ref ile köprülenir.
  const videoControlRef = useRef<{
    startVideo: (kind: "camera" | "screen") => Promise<void>;
    stopVideo: () => void;
    applyQuality: () => Promise<void>;
  } | null>(null);
  // Görüşme sırasında canlı mikrofon geçişi için köprü (connect effect'i içinde tanımlanır).
  const micControlRef = useRef<{ switchMic: () => Promise<void> } | null>(null);
  // Mikrofon track'i değişince konuşma-tespiti analyser'ının yeniden kurulmasını tetikler.
  const [micEpoch, setMicEpoch] = useState(0);
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

  // Deafen: tüm uzak sesleri kıs ve (Discord gibi) kendini de sustur. Kapanınca önceki mute durumuna dön.
  const applyDeafen = useCallback(
    (nextDeafened: boolean) => {
      setDeafened(nextDeafened);
      deafenedRef.current = nextDeafened;
      audioElsRef.current.forEach((el) => {
        el.muted = nextDeafened;
      });
      if (nextDeafened) {
        preDeafenMutedRef.current = mutedRef.current;
        applyMuted(true);
      } else {
        applyMuted(preDeafenMutedRef.current);
      }
      wsRef.current?.send(JSON.stringify({ type: "deafen", deafened: nextDeafened }));
    },
    [applyMuted],
  );

  const setRemoteVideoEnabled = useCallback((peerId: number, enabled: boolean) => {
    const next = new Set(ignoredRemoteVideoIdsRef.current);
    if (enabled) next.delete(peerId);
    else next.add(peerId);
    ignoredRemoteVideoIdsRef.current = next;
    setIgnoredRemoteVideoIds(next);

    remoteMediaRef.current.get(peerId)?.getVideoTracks().forEach((track) => {
      track.enabled = enabled;
    });

    // Yalnızca videoyu DOM'dan gizlemek veri akışını durdurmaz. Alıcı yönünü kapatarak
    // WebRTC yeniden pazarlığında karşı tarafın bu kullanıcıya video göndermesini keseriz.
    const peer = peersRef.current.get(peerId);
    peer?.pc.getTransceivers().forEach((transceiver) => {
      if (transceiver.receiver.track.kind !== "video") return;
      if (enabled) {
        if (transceiver.direction === "inactive") transceiver.direction = "recvonly";
        else if (transceiver.direction === "sendonly") transceiver.direction = "sendrecv";
      } else {
        if (transceiver.direction === "recvonly") transceiver.direction = "inactive";
        else if (transceiver.direction === "sendrecv") transceiver.direction = "sendonly";
      }
    });
  }, []);

  const toggleRemoteVideo = useCallback(
    (peerId: number) => {
      setRemoteVideoEnabled(peerId, ignoredRemoteVideoIdsRef.current.has(peerId));
    },
    [setRemoteVideoEnabled],
  );

  const cleanup = useCallback(() => {
    wsRef.current?.close();
    wsRef.current = null;
    peersRef.current.forEach((peer) => peer.pc.close());
    peersRef.current.clear();
    pendingIceRef.current.clear();
    audioElsRef.current.forEach((el) => {
      el.srcObject = null;
    });
    audioElsRef.current.clear();
    remoteMediaRef.current.clear();
    localStreamRef.current?.getTracks().forEach((track) => track.stop());
    localStreamRef.current = null;
    videoTrackRef.current?.stop();
    videoTrackRef.current = null;
    videoKindRef.current = null;
    setConnected(false);
    setParticipants([]);
    setMuted(false);
    setDeafened(false);
    setVideoKind(null);
    setLocalVideoStream(null);
    setRemoteStreams(new Map());
    ignoredRemoteVideoIdsRef.current = new Set();
    setIgnoredRemoteVideoIds(new Set());
    mutedRef.current = false;
    deafenedRef.current = false;
  }, []);

  useEffect(() => {
    if (!channelId) {
      cleanup();
      return;
    }

    let cancelled = false;
    let iceServers: RTCIceServer[] = [];
    let selfId = 0;
    let reconnectTimer: number | null = null;
    let reconnectDelay = 1000;
    let microphoneError: string | null = null;
    let microphoneAttempted = false;

    function upsertRemoteStream(peerId: number, stream: MediaStream) {
      setRemoteStreams((prev) => {
        const next = new Map(prev);
        next.set(peerId, stream);
        return next;
      });
    }

    function dropRemoteStream(peerId: number) {
      setRemoteStreams((prev) => {
        if (!prev.has(peerId)) return prev;
        const next = new Map(prev);
        next.delete(peerId);
        return next;
      });
    }

    function resetPeersForReconnect() {
      peersRef.current.forEach((peer) => peer.pc.close());
      peersRef.current.clear();
      pendingIceRef.current.clear();
      audioElsRef.current.forEach((element) => {
        element.srcObject = null;
      });
      audioElsRef.current.clear();
      remoteMediaRef.current.clear();
      setParticipants([]);
      setRemoteStreams(new Map());
    }

    function clearReconnectTimer() {
      if (reconnectTimer !== null) {
        window.clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
    }

    function scheduleReconnect() {
      if (cancelled || !navigator.onLine) return;
      clearReconnectTimer();
      const delay = Math.round(reconnectDelay * (0.85 + Math.random() * 0.3));
      reconnectDelay = Math.min(reconnectDelay * 2, 15_000);
      reconnectTimer = window.setTimeout(() => void connect(), delay);
    }

    function createPeerConnection(peerId: number, ws: WebSocket): PeerState {
      const existing = peersRef.current.get(peerId);
      if (existing) return existing;

      const pc = new RTCPeerConnection({ iceServers });
      // Politeness deterministik: büyük user_id "polite". Aynı anda iki taraf offer üretirse
      // (glare) polite taraf geri çekilir, böylece bağlantı kilitlenmez.
      // Her bağlantıda m-line sırasını baştan ve daima audio→video olarak sabitle. Sonradan
      // addTrack/removeTrack kullanmak Chrome'da yeni teklifin m-line sırasını değiştirip
      // setRemoteDescription hatasına yol açabiliyor.
      const audioTransceiver = pc.addTransceiver("audio", {
        direction: localStreamRef.current ? "sendrecv" : "recvonly",
      });
      if (localStreamRef.current) {
        const audioTrack = localStreamRef.current.getAudioTracks()[0];
        if (audioTrack) void audioTransceiver.sender.replaceTrack(audioTrack);
      }
      const sendingVideo = Boolean(videoTrackRef.current);
      const receivingVideo = !ignoredRemoteVideoIdsRef.current.has(peerId);
      const videoTransceiver = pc.addTransceiver("video", {
        direction: sendingVideo
          ? (receivingVideo ? "sendrecv" : "sendonly")
          : (receivingVideo ? "recvonly" : "inactive"),
      });
      const peer: PeerState = {
        pc,
        makingOffer: false,
        ignoreOffer: false,
        polite: selfId > peerId,
        videoSender: videoTransceiver.sender,
        videoTransceiver,
      };
      peersRef.current.set(peerId, peer);

      if (videoTrackRef.current && localVideoStreamForSend()) {
        void peer.videoSender.replaceTrack(videoTrackRef.current);
        void optimizeVideoSender(
          peer.videoSender,
          videoKindRef.current ?? "camera",
          voiceSettingsRef.current,
        );
      }

      pc.onnegotiationneeded = async () => {
        try {
          if (pc.signalingState !== "stable") return;
          peer.makingOffer = true;
          await pc.setLocalDescription();
          ws.send(JSON.stringify({ type: "offer", to: peerId, sdp: pc.localDescription?.sdp }));
        } catch (err) {
          setError(`Bağlantı pazarlığı hatası: ${err instanceof Error ? err.message : String(err)}`);
        } finally {
          peer.makingOffer = false;
        }
      };

      pc.onicecandidate = (event) => {
        if (event.candidate) {
          ws.send(JSON.stringify({ type: "ice-candidate", to: peerId, candidate: event.candidate }));
        }
      };

      pc.ontrack = (event) => {
        // Ses ve video AYRI stream'lerle (farklı MSID) gelebilir; her peer için tek bir birleşik
        // MediaStream'de track'leri biriktiririz. Böylece kamera/ekran açılınca ses stream'i
        // EZİLMEZ (karşı tarafın sesinin kesilmesi hatası).
        let ms = remoteMediaRef.current.get(peerId);
        if (!ms) {
          ms = new MediaStream();
          remoteMediaRef.current.set(peerId, ms);
        }
        const stream = ms;
        if (!stream.getTracks().includes(event.track)) {
          stream.addTrack(event.track);
        }
        if (event.track.kind === "video") {
          event.track.enabled = !ignoredRemoteVideoIdsRef.current.has(peerId);
        }

        // Ses her zaman gizli <audio> ile çalınır (video <video muted> ile gösterilir → çift ses olmaz).
        let audioEl = audioElsRef.current.get(peerId);
        if (!audioEl) {
          audioEl = new Audio();
          audioEl.autoplay = true;
          audioElsRef.current.set(peerId, audioEl);
        }
        if (audioEl.srcObject !== stream) {
          audioEl.srcObject = stream;
        }
        audioEl.muted = deafenedRef.current;
        void applySinkId(audioEl, voiceSettingsRef.current.outputDeviceId);
        upsertRemoteStream(peerId, stream);

        // Track susunca/bitince (ör. karşı taraf kamerayı kapatınca) döşemeyi güncelle/kaldır.
        const refresh = () => {
          if (event.track.readyState === "ended") {
            try {
              stream.removeTrack(event.track);
            } catch {
              /* yok say */
            }
          }
          if (remoteMediaRef.current.get(peerId) === stream) {
            upsertRemoteStream(peerId, stream);
          }
        };
        event.track.addEventListener("mute", refresh);
        event.track.addEventListener("unmute", refresh);
        event.track.addEventListener("ended", refresh);
      };

      pc.onconnectionstatechange = () => {
        if (pc.connectionState === "failed") {
          setError("WebRTC bağlantısı kurulamadı; TURN/firewall ayarlarını kontrol edin");
        }
      };

      return peer;
    }

    // Yerel video akışı gönderim için tek bir MediaStream olarak paketlenir (kamera veya ekran).
    let sendVideoStream: MediaStream | null = null;
    function localVideoStreamForSend(): MediaStream | null {
      return sendVideoStream;
    }

    async function flushPendingIce(peerId: number, pc: RTCPeerConnection) {
      const pending = pendingIceRef.current.get(peerId) ?? [];
      pendingIceRef.current.delete(peerId);
      for (const candidate of pending) {
        try {
          await pc.addIceCandidate(candidate);
        } catch {
          // yok sayılabilir (perfect negotiation: reddedilen offer'ın candidate'leri)
        }
      }
    }

    async function connect() {
      if (cancelled || !navigator.onLine) return;
      const currentSocket = wsRef.current;
      if (
        currentSocket &&
        (currentSocket.readyState === WebSocket.OPEN || currentSocket.readyState === WebSocket.CONNECTING)
      ) {
        return;
      }
      clearReconnectTimer();
      setError(null);
      try {
        const ice = await coreApi.voiceIceServers();
        if (cancelled) return;
        iceServers = ice.ice_servers;
      } catch (err) {
        setError(`TURN sunucusuna bağlanılamadı: ${err instanceof Error ? err.message : String(err)}`);
        scheduleReconnect();
        return;
      }

      if (!localStreamRef.current && !microphoneAttempted) {
        microphoneAttempted = true;
        try {
          const stream = await navigator.mediaDevices.getUserMedia({
            audio: buildAudioConstraints(voiceSettingsRef.current),
          });
          if (cancelled) {
            stream.getTracks().forEach((track) => track.stop());
            return;
          }
          localStreamRef.current = stream;
          microphoneError = null;
          if (voiceSettingsRef.current.mode === "ptt") {
            stream.getAudioTracks().forEach((track) => {
              track.enabled = false;
            });
            setMuted(true);
            mutedRef.current = true;
          }
        } catch (err) {
          microphoneError =
            `Mikrofona erişilemedi: ${err instanceof Error ? err.message : String(err)} ` +
            "(sadece dinleyici olarak katılıyorsunuz)";
          setError(microphoneError);
        }
      }

      const protocol = window.location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(
        `${protocol}://${window.location.host}/api/channels/${channelId}/voice?token=${getToken() ?? ""}`,
      );
      wsRef.current = ws;

      ws.onmessage = async (event) => {
        try {
          const data = JSON.parse(event.data) as SignalMessage;

          switch (data.type) {
          case "peers": {
            selfId = (data.self_id as number) ?? selfId;
            const peers = (data.peers as Omit<VoiceParticipant, "speaking">[]).map((p) => ({
              ...p,
              speaking: false,
            }));
            setParticipants(peers);
            setConnected(true);
            reconnectDelay = 1000;
            setError(microphoneError);
            // Mevcut herkesle bağlantı kur. Track ekleme onnegotiationneeded'i tetikleyip offer üretir.
            for (const peer of peers) {
              createPeerConnection(peer.user_id, ws);
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
                deafened: (data.deafened as boolean) ?? false,
                speaking: false,
              },
            ]);
            // Yeni gelen için de PC kur; iki taraf da offer üretebilir, glare perfect negotiation ile çözülür.
            createPeerConnection(data.user_id as number, ws);
            break;
          case "peer-left": {
            const peerId = data.user_id as number;
            peersRef.current.get(peerId)?.pc.close();
            peersRef.current.delete(peerId);
            audioElsRef.current.get(peerId)?.remove();
            audioElsRef.current.delete(peerId);
            remoteMediaRef.current.delete(peerId);
            dropRemoteStream(peerId);
            setParticipants((prev) => prev.filter((p) => p.user_id !== peerId));
            break;
          }
          case "offer": {
            const fromId = data.from as number;
            const peer = createPeerConnection(fromId, ws);
            const pc = peer.pc;
            const description: RTCSessionDescriptionInit = { type: "offer", sdp: data.sdp as string };
            const offerCollision = peer.makingOffer || pc.signalingState !== "stable";
            peer.ignoreOffer = !peer.polite && offerCollision;
            if (peer.ignoreOffer) break;
            // Polite eş yalnızca gerçekten yerel bir offer bekliyorsa rollback yapar.
            // makingOffer=true iken durum hâlâ stable olabilir; stable durumda rollback
            // çağırmak başlı başına InvalidStateError üretir.
            if (offerCollision && pc.signalingState === "have-local-offer") {
              await pc.setLocalDescription({ type: "rollback" });
            }
            await pc.setRemoteDescription(description);
            await flushPendingIce(fromId, pc);
            await pc.setLocalDescription();
            ws.send(JSON.stringify({ type: "answer", to: fromId, sdp: pc.localDescription?.sdp }));
            break;
          }
          case "answer": {
            const peer = peersRef.current.get(data.from as number);
            if (peer && peer.pc.signalingState === "have-local-offer") {
              await peer.pc.setRemoteDescription({ type: "answer", sdp: data.sdp as string });
              await flushPendingIce(data.from as number, peer.pc);
            }
            break;
          }
          case "ice-candidate": {
            const fromId = data.from as number;
            const candidate = data.candidate as RTCIceCandidateInit | undefined;
            if (candidate) {
              const peer = peersRef.current.get(fromId);
              if (peer?.pc.remoteDescription) {
                try {
                  await peer.pc.addIceCandidate(candidate);
                } catch (err) {
                  if (!peer.ignoreOffer) throw err;
                }
              } else {
                const pending = pendingIceRef.current.get(fromId) ?? [];
                pending.push(candidate);
                pendingIceRef.current.set(fromId, pending);
              }
            }
            break;
          }
          case "mute-changed":
            setParticipants((prev) =>
              prev.map((p) => (p.user_id === data.user_id ? { ...p, muted: data.muted as boolean } : p)),
            );
            break;
          case "deafen-changed":
            setParticipants((prev) =>
              prev.map((p) => (p.user_id === data.user_id ? { ...p, deafened: data.deafened as boolean } : p)),
            );
            break;
          case "speaking-changed":
            setParticipants((prev) =>
              prev.map((p) => (p.user_id === data.user_id ? { ...p, speaking: data.speaking as boolean } : p)),
            );
            break;
          }
        } catch (err) {
          setError(`WebRTC signaling hatası: ${err instanceof Error ? err.message : String(err)}`);
        }
      };

      ws.onerror = () => ws.close();
      ws.onclose = (event) => {
        if (wsRef.current === ws) wsRef.current = null;
        setConnected(false);
        if (cancelled) return;
        resetPeersForReconnect();
        if (event.code === 4401 || event.code === 4403 || event.code === 4404) {
          setError("Ses kanalına yeniden bağlanılamadı; oturum veya kanal yetkisini kontrol edin.");
          return;
        }
        setError("Ses bağlantısı kesildi, yeniden bağlanılıyor…");
        scheduleReconnect();
      };
    }

    // Video başlatma/durdurma yardımcıları connect kapsamında tanımlanır (peersRef üzerinden çalışır).
    async function startVideo(kind: "camera" | "screen") {
      try {
        const currentSettings = voiceSettingsRef.current;
        const camId = currentSettings.cameraDeviceId;
        const stream =
          kind === "camera"
            ? await navigator.mediaDevices.getUserMedia({
                video: buildCameraConstraints(currentSettings, camId),
              })
            : await navigator.mediaDevices.getDisplayMedia({
                video: buildScreenConstraints(currentSettings),
                audio: false,
              });
        const track = stream.getVideoTracks()[0];
        if (!track) return;

        track.contentHint = kind === "screen" ? "detail" : "motion";
        try {
          await track.applyConstraints(
            kind === "screen"
              ? buildScreenConstraints(currentSettings)
              : buildCameraConstraints(currentSettings, camId),
          );
        } catch {
          // Kaynağın desteklediği en yüksek mevcut çözünürlük ve kare hızı kullanılmaya devam eder.
        }

        videoTrackRef.current?.stop();
        videoTrackRef.current = track;
        videoKindRef.current = kind;
        sendVideoStream = stream;
        setLocalVideoStream(stream);
        setVideoKind(kind);

        // Kullanıcı tarayıcı arayüzünden paylaşımı durdurursa temizle.
        track.onended = () => stopVideo();

        for (const [peerId, peer] of peersRef.current) {
          await peer.videoSender.replaceTrack(track);
          peer.videoTransceiver.direction = ignoredRemoteVideoIdsRef.current.has(peerId)
            ? "sendonly"
            : "sendrecv";
          await optimizeVideoSender(peer.videoSender, kind, currentSettings);
        }
      } catch (err) {
        setError(`Video başlatılamadı: ${err instanceof Error ? err.message : String(err)}`);
      }
    }

    async function applyQuality() {
      const track = videoTrackRef.current;
      const kind = videoKindRef.current;
      if (!track || !kind) return;
      const currentSettings = voiceSettingsRef.current;
      try {
        await track.applyConstraints(
          kind === "screen"
            ? buildScreenConstraints(currentSettings)
            : buildCameraConstraints(currentSettings, null),
        );
      } catch {
        // Kaynak yeni tercihi tam desteklemiyorsa tarayıcının en yakın uygun değeri kullanılır.
      }
      for (const [, peer] of peersRef.current) {
        await optimizeVideoSender(peer.videoSender, kind, currentSettings);
      }
    }

    function stopVideo() {
      videoTrackRef.current?.stop();
      videoTrackRef.current = null;
      videoKindRef.current = null;
      sendVideoStream = null;
      setLocalVideoStream(null);
      setVideoKind(null);
      for (const [peerId, peer] of peersRef.current) {
        void peer.videoSender.replaceTrack(null);
        peer.videoTransceiver.direction = ignoredRemoteVideoIdsRef.current.has(peerId)
          ? "inactive"
          : "recvonly";
      }
    }

    // Görüşmeden çıkmadan mikrofon/ses işleme ayarını değiştir: yeni track'i al, tüm audio
    // sender'larda replaceTrack yap (yeniden pazarlık gerekmez), eskiyi durdur.
    async function switchMic() {
      try {
        const newStream = await navigator.mediaDevices.getUserMedia({
          audio: buildAudioConstraints(voiceSettingsRef.current),
        });
        const newTrack = newStream.getAudioTracks()[0];
        if (!newTrack) return;
        newTrack.enabled = !mutedRef.current;
        for (const [, peer] of peersRef.current) {
          const sender = peer.pc.getSenders().find((s) => s.track && s.track.kind === "audio");
          if (sender) await sender.replaceTrack(newTrack);
        }
        localStreamRef.current?.getAudioTracks().forEach((t) => t.stop());
        localStreamRef.current = newStream;
        setMicEpoch((e) => e + 1); // konuşma-tespiti analyser'ını yeni track'le yeniden kur
      } catch (err) {
        setError(`Mikrofon değiştirilemedi: ${err instanceof Error ? err.message : String(err)}`);
      }
    }

    videoControlRef.current = { startVideo, stopVideo, applyQuality };
    micControlRef.current = { switchMic };

    function handleOnline() {
      reconnectDelay = 1000;
      void connect();
    }

    window.addEventListener("online", handleOnline);
    connect();

    return () => {
      cancelled = true;
      clearReconnectTimer();
      window.removeEventListener("online", handleOnline);
      videoControlRef.current = null;
      micControlRef.current = null;
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
    analyser.fftSize = 256;
    source.connect(analyser);
    const buffer = new Uint8Array(analyser.frequencyBinCount);

    let lastSpeaking = false;
    let timerId: number | null = null;

    function reportSpeaking(speaking: boolean) {
      if (speaking === lastSpeaking) return;
      lastSpeaking = speaking;
      wsRef.current?.send(JSON.stringify({ type: "speaking", speaking }));
    }

    function tick() {
      if (document.hidden) return;
      analyser.getByteFrequencyData(buffer);
      const average = buffer.reduce((sum, value) => sum + value, 0) / buffer.length;
      const speaking = average > SPEAKING_THRESHOLD && !mutedRef.current;
      reportSpeaking(speaking);
      // Konuşma göstergesi için 60 Hz gereksiz; ~13 Hz CPU tüketimini belirgin azaltır.
      timerId = window.setTimeout(tick, 75);
    }

    function handleVisibilityChange() {
      if (timerId !== null) {
        window.clearTimeout(timerId);
        timerId = null;
      }
      if (document.hidden) {
        reportSpeaking(false);
        void audioContext.suspend();
      } else {
        void audioContext.resume().then(tick).catch(() => {});
      }
    }

    document.addEventListener("visibilitychange", handleVisibilityChange);
    if (document.hidden) {
      void audioContext.suspend();
    } else {
      tick();
    }

    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      if (timerId !== null) window.clearTimeout(timerId);
      reportSpeaking(false);
      source.disconnect();
      void audioContext.close();
    };
  }, [connected, micEpoch]);

  // Çıkış cihazı (hoparlör) değişince mevcut uzak ses elemanlarına uygula.
  useEffect(() => {
    audioElsRef.current.forEach((el) => void applySinkId(el, voiceSettings.outputDeviceId));
  }, [voiceSettings.outputDeviceId]);

  // Mikrofon veya ses işleme ayarı değişince, görüşme sürüyorsa canlı geçiş yap.
  useEffect(() => {
    if (connected) void micControlRef.current?.switchMic();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    voiceSettings.inputDeviceId,
    voiceSettings.noiseSuppression,
    voiceSettings.echoCancellation,
    voiceSettings.autoGainControl,
  ]);

  // Çözünürlük/FPS tercihi değişince devam eden kamera veya ekran paylaşımına anında uygula.
  useEffect(() => {
    if (connected && videoKindRef.current) void videoControlRef.current?.applyQuality();
  }, [connected, voiceSettings.videoFrameRate, voiceSettings.videoQuality]);

  const toggleMute = useCallback(() => {
    // Deafen açıkken mute'u tek başına değiştirmek Discord'da mümkün değil; önce deafen'i kapat.
    if (deafenedRef.current) {
      applyDeafen(false);
      return;
    }
    applyMuted(!mutedRef.current);
  }, [applyMuted, applyDeafen]);

  const toggleDeafen = useCallback(() => {
    applyDeafen(!deafenedRef.current);
  }, [applyDeafen]);

  const toggleCamera = useCallback(() => {
    if (videoKind === "camera") {
      videoControlRef.current?.stopVideo();
    } else {
      void videoControlRef.current?.startVideo("camera");
    }
  }, [videoKind]);

  const toggleScreenShare = useCallback(() => {
    if (videoKind === "screen") {
      videoControlRef.current?.stopVideo();
    } else {
      void videoControlRef.current?.startVideo("screen");
    }
  }, [videoKind]);

  const handlePttChange = useCallback(
    (active: boolean) => {
      applyMuted(!active);
    },
    [applyMuted],
  );
  usePushToTalk(connected && voiceSettings.mode === "ptt", voiceSettings.pttCombo, handlePttChange);

  return {
    connected,
    participants,
    muted,
    deafened,
    videoKind,
    localVideoStream,
    remoteStreams,
    ignoredRemoteVideoIds,
    error,
    toggleMute,
    toggleDeafen,
    toggleCamera,
    toggleScreenShare,
    toggleRemoteVideo,
    disconnect: cleanup,
  };
}

export type VoiceChannelState = ReturnType<typeof useVoiceChannel>;
