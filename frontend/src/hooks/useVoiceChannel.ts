import { useCallback, useEffect, useRef, useState } from "react";

import { coreApi, getToken } from "../api/client";
import { webSocketUrl } from "../desktopBridge";
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
  avatar_url?: string | null;
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
  negotiationEnabled: boolean;
  negotiationPending: boolean;
  requestNegotiation: () => void;
  cameraSender: RTCRtpSender;
  cameraTransceiver: RTCRtpTransceiver;
  screenSender: RTCRtpSender;
  screenTransceiver: RTCRtpTransceiver;
}

export interface RemoteVideoStream {
  userId: number;
  kind: "camera" | "screen";
  stream: MediaStream;
}

const SPEAKING_THRESHOLD = 12;
const SIGNALING_TIMEOUT_MS = 6_000;
const ICE_CONFIG_TIMEOUT_MS = 1_600;
const DEFAULT_ICE_SERVERS: RTCIceServer[] = [
  { urls: "stun:stun.cloudflare.com:3478" },
  { urls: "stun:stun.l.google.com:19302" },
];

function rejectAfter<T>(promise: Promise<T>, timeoutMs: number, message: string): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = window.setTimeout(() => reject(new Error(message)), timeoutMs);
    promise.then(
      (value) => {
        window.clearTimeout(timer);
        resolve(value);
      },
      (error) => {
        window.clearTimeout(timer);
        reject(error);
      },
    );
  });
}

function microphoneErrorMessage(error: unknown): string {
  if (error instanceof DOMException) {
    if (error.name === "NotAllowedError" || error.name === "SecurityError") {
      return "Mikrofon izni verilmedi. Adres çubuğundaki kilit simgesinden mikrofonu açıp kanala yeniden katılın.";
    }
    if (error.name === "NotFoundError") return "Kullanılabilir bir mikrofon bulunamadı.";
    if (error.name === "NotReadableError") return "Mikrofon başka bir uygulama tarafından kullanılıyor.";
  }
  return `Mikrofona erişilemedi: ${error instanceof Error ? error.message : String(error)}`;
}

function sendWebSocketJson(socket: WebSocket | null, payload: unknown): boolean {
  if (!socket || socket.readyState !== WebSocket.OPEN) return false;
  try {
    socket.send(JSON.stringify(payload));
    return true;
  } catch {
    return false;
  }
}

function isExpectedConnectionAbort(error: unknown): boolean {
  if (!(error instanceof Error)) return false;
  const detail = `${error.name} ${error.message}`.toLowerCase();
  return (
    error.name === "AbortError" ||
    detail.includes("connection aborted") ||
    detail.includes("operation was aborted") ||
    detail.includes("peerconnection is closed") ||
    detail.includes("connection is closed")
  );
}

function buildCameraConstraints(vs: VoiceSettings, deviceId: string | null): MediaTrackConstraints {
  const preset = VIDEO_QUALITY_PRESETS[vs.videoQuality];
  return {
    ...(deviceId ? { deviceId: { exact: deviceId } } : {}),
    width: { ideal: preset.width, max: preset.width },
    height: { ideal: preset.height, max: preset.height },
    frameRate: { ideal: vs.videoFrameRate, max: vs.videoFrameRate },
  };
}

function buildScreenConstraints(vs: VoiceSettings): MediaTrackConstraints {
  // Ekranın doğal en-boy oranını koru. Aynı anda width/height üst sınırı istemek bazı
  // tarayıcılarda paylaşımı hedef oranına kırpar. Çözünürlük sınırı aşağıda WebRTC
  // encoder'ında orantılı ölçeklenir; kaynak görüntünün hiçbir kenarı kaybolmaz.
  return {
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
    if (kind === "screen") {
      const source = sender.track?.getSettings();
      const sourceWidth = source?.width ?? preset.width;
      const sourceHeight = source?.height ?? preset.height;
      const proportionalScale = Math.max(
        1,
        sourceWidth / preset.width,
        sourceHeight / preset.height,
      );
      parameters.encodings[0].scaleResolutionDownBy =
        Math.round(proportionalScale * 100) / 100;
    }
    parameters.degradationPreference = "maintain-resolution";
    await sender.setParameters(parameters);
  } catch {
    // Bazı tarayıcılar kodlayıcı parametrelerinin bir kısmını desteklemez; varsayılan uyarlama sürer.
  }
}

function videoDirection(
  hasLocalTrack: boolean,
  receivingRemoteVideo: boolean,
): RTCRtpTransceiverDirection {
  // Video m-line'larını normal durumda baştan sendrecv pazarlamak bilinçlidir. Sender'da
  // henüz track olmasa bile daha sonra replaceTrack(track) ile kamera/yayın başlatılabilir;
  // böylece her açma işleminde kaybolabilen ayrı bir SDP yeniden-pazarlık turuna gerek kalmaz.
  if (receivingRemoteVideo) return "sendrecv";
  return hasLocalTrack ? "sendonly" : "inactive";
}

export function useVoiceChannel(channelId: number | null, voiceSettings: VoiceSettings) {
  const [connected, setConnected] = useState(false);
  const [participants, setParticipants] = useState<VoiceParticipant[]>([]);
  const [muted, setMuted] = useState(false);
  const [deafened, setDeafened] = useState(false);
  const [localCameraStream, setLocalCameraStream] = useState<MediaStream | null>(null);
  const [localScreenStream, setLocalScreenStream] = useState<MediaStream | null>(null);
  const [remoteStreams, setRemoteStreams] = useState<Map<string, RemoteVideoStream>>(new Map());
  const [ignoredRemoteVideoIds, setIgnoredRemoteVideoIds] = useState<Set<number>>(new Set());
  const [error, setError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const localStreamRef = useRef<MediaStream | null>(null); // mikrofon (audio)
  const microphoneSourceRef = useRef<MediaStream | null>(null);
  const microphoneGraphRef = useRef<{ context: AudioContext; gain: GainNode } | null>(null);
  const cameraTrackRef = useRef<MediaStreamTrack | null>(null);
  const screenTrackRef = useRef<MediaStreamTrack | null>(null);
  const peersRef = useRef<Map<number, PeerState>>(new Map());
  const pendingIceRef = useRef<Map<number, RTCIceCandidateInit[]>>(new Map());
  const audioElsRef = useRef<Map<number, HTMLAudioElement>>(new Map());
  // Her peer için tek bir birleşik uzak MediaStream. Ses ve video ayrı MSID'lerle gelse de
  // aynı stream'de biriktirilir; böylece video eklenince ses stream'i ezilmez (Hata 1).
  const remoteMediaRef = useRef<Map<string, MediaStream>>(new Map());
  const ignoredRemoteVideoIdsRef = useRef<Set<number>>(new Set());
  const mutedRef = useRef(false);
  const deafenedRef = useRef(false);
  const preDeafenMutedRef = useRef(false); // deafen açılmadan önceki mute durumu
  // Video kontrol fonksiyonları connect effect'i içinde tanımlanır; dışarıya sabit ref ile köprülenir.
  const videoControlRef = useRef<{
    startVideo: (kind: "camera" | "screen") => Promise<void>;
    stopVideo: (kind: "camera" | "screen") => void;
    applyQuality: () => Promise<void>;
  } | null>(null);
  // Görüşme sırasında canlı mikrofon geçişi için köprü (connect effect'i içinde tanımlanır).
  const micControlRef = useRef<{ switchMic: () => Promise<void> } | null>(null);
  // Mikrofon track'i değişince konuşma-tespiti analyser'ının yeniden kurulmasını tetikler.
  const [micEpoch, setMicEpoch] = useState(0);
  // connect() effect'i sadece channelId'ye bağlı çalışır; bağlantı anındaki modu okumak için ref kullanılır.
  const voiceSettingsRef = useRef(voiceSettings);
  voiceSettingsRef.current = voiceSettings;

  const processMicrophoneStream = useCallback(async (sourceStream: MediaStream) => {
    const context = new AudioContext();
    const source = context.createMediaStreamSource(sourceStream);
    const gain = context.createGain();
    const destination = context.createMediaStreamDestination();
    gain.gain.value = Math.max(0, Math.min(2, voiceSettingsRef.current.inputVolume / 100));
    source.connect(gain);
    gain.connect(destination);
    await context.resume().catch(() => {});

    microphoneSourceRef.current?.getTracks().forEach((track) => track.stop());
    void microphoneGraphRef.current?.context.close();
    microphoneSourceRef.current = sourceStream;
    microphoneGraphRef.current = { context, gain };
    return destination.stream;
  }, []);

  const applyMuted = useCallback((nextMuted: boolean) => {
    setMuted(nextMuted);
    mutedRef.current = nextMuted;
    localStreamRef.current?.getAudioTracks().forEach((track) => {
      track.enabled = !nextMuted;
    });
    sendWebSocketJson(wsRef.current, { type: "mute", muted: nextMuted });
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
      sendWebSocketJson(wsRef.current, { type: "deafen", deafened: nextDeafened });
    },
    [applyMuted],
  );

  const setRemoteVideoEnabled = useCallback((peerId: number, enabled: boolean) => {
    const next = new Set(ignoredRemoteVideoIdsRef.current);
    if (enabled) next.delete(peerId);
    else next.add(peerId);
    ignoredRemoteVideoIdsRef.current = next;
    setIgnoredRemoteVideoIds(next);

    for (const [key, stream] of remoteMediaRef.current) {
      if (key.startsWith(`${peerId}:`)) stream.getVideoTracks().forEach((track) => { track.enabled = enabled; });
    }

    // Yalnızca videoyu DOM'dan gizlemek veri akışını durdurmaz. Alıcı yönünü kapatarak
    // WebRTC yeniden pazarlığında karşı tarafın bu kullanıcıya video göndermesini keseriz.
    const peer = peersRef.current.get(peerId);
    if (peer) {
      const videoTransceivers = [
        [peer.cameraTransceiver, cameraTrackRef.current],
        [peer.screenTransceiver, screenTrackRef.current],
      ] as const;
      let directionChanged = false;
      for (const [transceiver, localTrack] of videoTransceivers) {
        const nextDirection = videoDirection(Boolean(localTrack), enabled);
        if (transceiver.direction === nextDirection) continue;
        transceiver.direction = nextDirection;
        directionChanged = true;
      }
      if (directionChanged) peer.requestNegotiation();
    }
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
    microphoneSourceRef.current?.getTracks().forEach((track) => track.stop());
    microphoneSourceRef.current = null;
    void microphoneGraphRef.current?.context.close();
    microphoneGraphRef.current = null;
    cameraTrackRef.current?.stop();
    screenTrackRef.current?.stop();
    cameraTrackRef.current = null;
    screenTrackRef.current = null;
    setConnected(false);
    setParticipants([]);
    setMuted(false);
    setDeafened(false);
    setLocalCameraStream(null);
    setLocalScreenStream(null);
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
    let iceServers: RTCIceServer[] = DEFAULT_ICE_SERVERS;
    let selfId = 0;
    let reconnectTimer: number | null = null;
    let reconnectDelay = 250;
    let microphoneError: string | null = null;
    let microphoneAttempted = false;
    let socketHandshakeTimer: number | null = null;
    let handshakeTimedOut = false;
    const peerRecoveryTimers = new Map<number, number>();

    function upsertRemoteStream(peerId: number, kind: "camera" | "screen", stream: MediaStream) {
      const key = `${peerId}:${kind}`;
      setRemoteStreams((prev) => {
        const next = new Map(prev);
        next.set(key, { userId: peerId, kind, stream });
        return next;
      });
    }

    function dropRemoteStream(peerId: number) {
      setRemoteStreams((prev) => {
        const next = new Map(
          [...prev].filter(([, value]) => value.userId !== peerId),
        );
        return next;
      });
    }

    function closePeerConnection(peerId: number) {
      const recoveryTimer = peerRecoveryTimers.get(peerId);
      if (recoveryTimer !== undefined) window.clearTimeout(recoveryTimer);
      peerRecoveryTimers.delete(peerId);
      peersRef.current.get(peerId)?.pc.close();
      peersRef.current.delete(peerId);
      const audioElement = audioElsRef.current.get(peerId);
      if (audioElement) audioElement.srcObject = null;
      audioElsRef.current.delete(peerId);
      for (const key of [...remoteMediaRef.current.keys()]) {
        if (key.startsWith(`${peerId}:`)) remoteMediaRef.current.delete(key);
      }
      pendingIceRef.current.delete(peerId);
      dropRemoteStream(peerId);
    }

    function resetPeersForReconnect() {
      peerRecoveryTimers.forEach((timer) => window.clearTimeout(timer));
      peerRecoveryTimers.clear();
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

    function clearSocketHandshakeTimer() {
      if (socketHandshakeTimer !== null) {
        window.clearTimeout(socketHandshakeTimer);
        socketHandshakeTimer = null;
      }
    }

    function scheduleReconnect() {
      if (cancelled || !navigator.onLine) return;
      clearReconnectTimer();
      const delay = Math.round(reconnectDelay * (0.85 + Math.random() * 0.3));
      reconnectDelay = Math.min(reconnectDelay * 2, 5_000);
      reconnectTimer = window.setTimeout(() => void connect(), delay);
    }

    function createPeerConnection(
      peerId: number,
      ws: WebSocket,
      initiateNegotiation = true,
    ): PeerState {
      const existing = peersRef.current.get(peerId);
      if (existing) return existing;

      const pc = new RTCPeerConnection({
        iceServers,
        bundlePolicy: "max-bundle",
        iceCandidatePoolSize: 2,
      });
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
      const receivingVideo = !ignoredRemoteVideoIdsRef.current.has(peerId);
      const cameraTransceiver = pc.addTransceiver("video", {
        direction: videoDirection(Boolean(cameraTrackRef.current), receivingVideo),
      });
      const screenTransceiver = pc.addTransceiver("video", {
        direction: videoDirection(Boolean(screenTrackRef.current), receivingVideo),
      });
      const peer: PeerState = {
        pc,
        makingOffer: false,
        ignoreOffer: false,
        polite: selfId > peerId,
        negotiationEnabled: initiateNegotiation,
        negotiationPending: false,
        requestNegotiation: () => {},
        cameraSender: cameraTransceiver.sender,
        cameraTransceiver,
        screenSender: screenTransceiver.sender,
        screenTransceiver,
      };
      peersRef.current.set(peerId, peer);

      if (cameraTrackRef.current) {
        void peer.cameraSender.replaceTrack(cameraTrackRef.current);
        void optimizeVideoSender(
          peer.cameraSender,
          "camera",
          voiceSettingsRef.current,
        );
      }
      if (screenTrackRef.current) {
        void peer.screenSender.replaceTrack(screenTrackRef.current);
        void optimizeVideoSender(peer.screenSender, "screen", voiceSettingsRef.current);
      }

      async function negotiate() {
        if (peer.makingOffer) return;
        if (
          !peer.negotiationEnabled ||
          pc.signalingState !== "stable"
        ) {
          peer.negotiationPending = true;
          return;
        }
        try {
          peer.negotiationPending = false;
          peer.makingOffer = true;
          await pc.setLocalDescription();
          sendWebSocketJson(ws, { type: "offer", to: peerId, sdp: pc.localDescription?.sdp });
        } catch (err) {
          if (
            cancelled ||
            wsRef.current !== ws ||
            peersRef.current.get(peerId)?.pc !== pc ||
            isExpectedConnectionAbort(err)
          ) return;
          setError(`Bağlantı pazarlığı hatası: ${err instanceof Error ? err.message : String(err)}`);
        } finally {
          peer.makingOffer = false;
          if (peer.negotiationPending && pc.signalingState === "stable") {
            queueMicrotask(() => void negotiate());
          }
        }
      }

      pc.onnegotiationneeded = () => {
        void negotiate();
      };
      peer.requestNegotiation = () => {
        peer.negotiationPending = true;
        void negotiate();
      };

      pc.onicecandidate = (event) => {
        if (event.candidate) {
          sendWebSocketJson(ws, { type: "ice-candidate", to: peerId, candidate: event.candidate });
        }
      };

      pc.ontrack = (event) => {
        const transceiverIndex = pc.getTransceivers().indexOf(event.transceiver);
        const isCamera = event.transceiver === peer.cameraTransceiver || transceiverIndex === 1;
        const isScreen = event.transceiver === peer.screenTransceiver || transceiverIndex === 2;
        if (event.track.kind === "audio") {
          const stream = event.streams[0] ?? new MediaStream([event.track]);
          let audioEl = audioElsRef.current.get(peerId);
          if (!audioEl) {
            audioEl = new Audio();
            audioEl.autoplay = true;
            audioElsRef.current.set(peerId, audioEl);
          }
          audioEl.srcObject = stream;
          audioEl.muted = deafenedRef.current;
          audioEl.volume = Math.max(0, Math.min(1, voiceSettingsRef.current.outputVolume / 100));
          void applySinkId(audioEl, voiceSettingsRef.current.outputDeviceId);
          return;
        }
        if (!isCamera && !isScreen) return;
        const kind = isScreen ? "screen" : "camera";
        const key = `${peerId}:${kind}`;
        const stream = new MediaStream([event.track]);
        remoteMediaRef.current.set(key, stream);
        event.track.enabled = !ignoredRemoteVideoIdsRef.current.has(peerId);
        upsertRemoteStream(peerId, kind, stream);

        // Track susunca/bitince (ör. karşı taraf kamerayı kapatınca) döşemeyi güncelle/kaldır.
        const refresh = () => {
          if (event.track.readyState === "ended") {
            remoteMediaRef.current.delete(key);
          }
          upsertRemoteStream(peerId, kind, stream);
        };
        event.track.addEventListener("mute", refresh);
        event.track.addEventListener("unmute", refresh);
        event.track.addEventListener("ended", refresh);
      };

      pc.onconnectionstatechange = () => {
        const previousTimer = peerRecoveryTimers.get(peerId);
        if (previousTimer !== undefined) {
          window.clearTimeout(previousTimer);
          peerRecoveryTimers.delete(peerId);
        }
        if (pc.connectionState === "connected") {
          setError((current) =>
            current === "Medya bağlantısı yeniden kuruluyor…" ? microphoneError : current,
          );
          return;
        }
        if (pc.connectionState === "disconnected" || pc.connectionState === "failed") {
          const delay = pc.connectionState === "failed" ? 1_000 : 8_000;
          const timer = window.setTimeout(() => {
            peerRecoveryTimers.delete(peerId);
            if (
              cancelled ||
              peersRef.current.get(peerId)?.pc !== pc ||
              !["disconnected", "failed"].includes(pc.connectionState)
            ) return;
            setError("Medya bağlantısı yeniden kuruluyor…");
            try {
              pc.restartIce();
            } catch {
              // Socket yeniden bağlanırken kapanan eski peer'i canlandırmaya çalışma.
            }
          }, delay);
          peerRecoveryTimers.set(peerId, timer);
        }
      };

      return peer;
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
      if (!window.isSecureContext) {
        setError(
          "Sesli sohbet güvenli bir HTTPS bağlantısı gerektirir. Sertifika uyarısını geçmeyin; https://cekin.gen.tr adresini kullanın.",
        );
        return;
      }
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
        const ice = await rejectAfter(
          coreApi.voiceIceServers(),
          ICE_CONFIG_TIMEOUT_MS,
          "Ses sunucusu zaman aşımına uğradı",
        );
        if (cancelled) return;
        if (ice.ice_servers.length) iceServers = ice.ice_servers;
      } catch {
        // Ayar uç noktası geçici olarak 502 verse bile sesliyi durdurma. Genel STUN
        // yedeğiyle hemen devam et; sonraki reconnect sunucu ayarını yeniden alır.
        iceServers = DEFAULT_ICE_SERVERS;
      }

      if (!localStreamRef.current && !microphoneAttempted) {
        microphoneAttempted = true;
        try {
          if (!navigator.mediaDevices?.getUserMedia) {
            throw new DOMException("Secure media API unavailable", "SecurityError");
          }
          const sourceStream = await navigator.mediaDevices.getUserMedia({
            audio: buildAudioConstraints(voiceSettingsRef.current),
          });
          const stream = await processMicrophoneStream(sourceStream);
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
          microphoneError = `${microphoneErrorMessage(err)} (yalnız dinleyici olarak katılıyorsunuz)`;
          setError(microphoneError);
        }
      }

      let ws: WebSocket;
      try {
        ws = new WebSocket(
          `${webSocketUrl(`/channels/${channelId}/voice`)}?token=${encodeURIComponent(getToken() ?? "")}`,
        );
      } catch (err) {
        setError(`Ses bağlantısı başlatılamadı: ${err instanceof Error ? err.message : String(err)}`);
        scheduleReconnect();
        return;
      }
      wsRef.current = ws;
      handshakeTimedOut = false;
      clearSocketHandshakeTimer();
      socketHandshakeTimer = window.setTimeout(() => {
        if (cancelled || wsRef.current !== ws || connected) return;
        handshakeTimedOut = true;
        setError(
          "Ses sinyal sunucusu 6 saniye içinde yanıt vermedi; yeniden bağlanılıyor…",
        );
        ws.close();
      }, SIGNALING_TIMEOUT_MS);

      // WebSocket message event'leri async handler'ı beklemez. SDP offer/answer işlemlerini
      // tek kuyrukta işleyerek aynı RTCPeerConnection üzerinde yarışmalarını engelle.
      let signalingQueue = Promise.resolve();
      ws.onmessage = (event) => {
        signalingQueue = signalingQueue.then(async () => {
          if (cancelled || wsRef.current !== ws) return;
          try {
          const data = JSON.parse(event.data) as SignalMessage;

          switch (data.type) {
          case "peers": {
            clearSocketHandshakeTimer();
            selfId = (data.self_id as number) ?? selfId;
            const peers = (data.peers as Omit<VoiceParticipant, "speaking">[]).map((p) => ({
              ...p,
              speaking: false,
            }));
            setParticipants(peers);
            setConnected(true);
            reconnectDelay = 250;
            setError(microphoneError);
            // Mevcut herkesle bağlantı kur. Track ekleme onnegotiationneeded'i tetikleyip offer üretir.
            for (const peer of peers) {
              createPeerConnection(peer.user_id, ws, true);
            }
            break;
          }
          case "peer-joined": {
            const joinedUserId = data.user_id as number;
            const participant = {
                user_id: joinedUserId,
                username: data.username as string,
                avatar_url: (data.avatar_url as string | null) ?? null,
                muted: data.muted as boolean,
                deafened: (data.deafened as boolean) ?? false,
                speaking: false,
            };
            setParticipants((prev) => [
              ...prev.filter((item) => item.user_id !== joinedUserId),
              participant,
            ]);
            // Aynı kullanıcı F5/reconnect yaptıysa eski peer'i kapatıp yeni oturumla temiz
            // bağlantı kur. Eski peer üzerinde yeni SDP uygulamak connection-aborted yarışı doğurur.
            if (peersRef.current.has(joinedUserId)) closePeerConnection(joinedUserId);
            // Teklif üretme sorumluluğu yeni katılanda. Bu taraf PC'yi cevap vermeye hazırlar;
            // aynı anda iki offer üretilmediği için ses/video m-line'ları karışmaz.
            createPeerConnection(joinedUserId, ws, false);
            break;
          }
          case "peer-left": {
            const peerId = data.user_id as number;
            closePeerConnection(peerId);
            setParticipants((prev) => prev.filter((p) => p.user_id !== peerId));
            break;
          }
          case "offer": {
            const fromId = data.from as number;
            const peer = createPeerConnection(fromId, ws, false);
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
            sendWebSocketJson(ws, { type: "answer", to: fromId, sdp: pc.localDescription?.sdp });
            peer.negotiationEnabled = true;
            peer.negotiationPending = false;
            break;
          }
          case "answer": {
            const peer = peersRef.current.get(data.from as number);
            if (peer && peer.pc.signalingState === "have-local-offer") {
              await peer.pc.setRemoteDescription({ type: "answer", sdp: data.sdp as string });
              await flushPendingIce(data.from as number, peer.pc);
              peer.negotiationEnabled = true;
              if (peer.negotiationPending) peer.requestNegotiation();
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
            if (
              cancelled ||
              wsRef.current !== ws ||
              isExpectedConnectionAbort(err)
            ) return;
            setError(`WebRTC signaling hatası: ${err instanceof Error ? err.message : String(err)}`);
          }
        });
      };

      ws.onerror = () => ws.close();
      ws.onclose = (event) => {
        clearSocketHandshakeTimer();
        if (wsRef.current === ws) wsRef.current = null;
        setConnected(false);
        if (cancelled) return;
        resetPeersForReconnect();
        if (event.code === 4401 || event.code === 4403 || event.code === 4404) {
          setError("Ses kanalına yeniden bağlanılamadı; oturum veya kanal yetkisini kontrol edin.");
          return;
        }
        if (handshakeTimedOut) {
          scheduleReconnect();
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

        const trackRef = kind === "camera" ? cameraTrackRef : screenTrackRef;
        trackRef.current?.stop();
        trackRef.current = track;
        if (kind === "camera") setLocalCameraStream(stream);
        else setLocalScreenStream(stream);

        // Kullanıcı tarayıcı arayüzünden paylaşımı durdurursa temizle.
        track.onended = () => stopVideo(kind);

        for (const [peerId, peer] of peersRef.current) {
          const sender = kind === "camera" ? peer.cameraSender : peer.screenSender;
          const transceiver = kind === "camera" ? peer.cameraTransceiver : peer.screenTransceiver;
          await sender.replaceTrack(track);
          const nextDirection = videoDirection(
            true,
            !ignoredRemoteVideoIdsRef.current.has(peerId),
          );
          const directionChanged = transceiver.direction !== nextDirection;
          if (directionChanged) transceiver.direction = nextDirection;
          await optimizeVideoSender(sender, kind, currentSettings);
          // Normal akışta m-line zaten sendrecv'dir; replaceTrack tek başına yayını başlatır.
          // Kullanıcı bu eşin videosunu özellikle kapattıysa sendonly'ye geçiş SDP gerektirir.
          if (directionChanged) peer.requestNegotiation();
        }
      } catch (err) {
        setError(`Video başlatılamadı: ${err instanceof Error ? err.message : String(err)}`);
      }
    }

    async function applyQuality() {
      const currentSettings = voiceSettingsRef.current;
      for (const kind of ["camera", "screen"] as const) {
        const track = kind === "camera" ? cameraTrackRef.current : screenTrackRef.current;
        if (!track) continue;
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
          await optimizeVideoSender(
            kind === "camera" ? peer.cameraSender : peer.screenSender,
            kind,
            currentSettings,
          );
        }
      }
    }

    function stopVideo(kind: "camera" | "screen") {
      const trackRef = kind === "camera" ? cameraTrackRef : screenTrackRef;
      const track = trackRef.current;
      trackRef.current = null;
      track?.stop();
      if (kind === "camera") setLocalCameraStream(null);
      else setLocalScreenStream(null);
      for (const [peerId, peer] of peersRef.current) {
        const sender = kind === "camera" ? peer.cameraSender : peer.screenSender;
        const transceiver = kind === "camera" ? peer.cameraTransceiver : peer.screenTransceiver;
        void sender.replaceTrack(null);
        const nextDirection = videoDirection(
          false,
          !ignoredRemoteVideoIdsRef.current.has(peerId),
        );
        const directionChanged = transceiver.direction !== nextDirection;
        if (directionChanged) {
          transceiver.direction = nextDirection;
          peer.requestNegotiation();
        }
      }
    }

    // Görüşmeden çıkmadan mikrofon/ses işleme ayarını değiştir: yeni track'i al, tüm audio
    // sender'larda replaceTrack yap (yeniden pazarlık gerekmez), eskiyi durdur.
    async function switchMic() {
      try {
        const newStream = await navigator.mediaDevices.getUserMedia({
          audio: buildAudioConstraints(voiceSettingsRef.current),
        });
        const processedStream = await processMicrophoneStream(newStream);
        const newTrack = processedStream.getAudioTracks()[0];
        if (!newTrack) return;
        newTrack.enabled = !mutedRef.current;
        for (const [, peer] of peersRef.current) {
          const sender = peer.pc.getSenders().find((s) => s.track && s.track.kind === "audio");
          if (sender) await sender.replaceTrack(newTrack);
        }
        localStreamRef.current?.getAudioTracks().forEach((t) => t.stop());
        localStreamRef.current = processedStream;
        setMicEpoch((e) => e + 1); // konuşma-tespiti analyser'ını yeni track'le yeniden kur
      } catch (err) {
        setError(`Mikrofon değiştirilemedi: ${err instanceof Error ? err.message : String(err)}`);
      }
    }

    videoControlRef.current = { startVideo, stopVideo, applyQuality };
    micControlRef.current = { switchMic };

    function handleOnline() {
      reconnectDelay = 250;
      void connect();
    }

    window.addEventListener("online", handleOnline);
    connect();

    return () => {
      cancelled = true;
      clearReconnectTimer();
      clearSocketHandshakeTimer();
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
      sendWebSocketJson(wsRef.current, { type: "speaking", speaking });
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
    audioElsRef.current.forEach((el) => {
      el.volume = Math.max(0, Math.min(1, voiceSettings.outputVolume / 100));
      void applySinkId(el, voiceSettings.outputDeviceId);
    });
  }, [voiceSettings.outputDeviceId, voiceSettings.outputVolume]);

  useEffect(() => {
    const gain = microphoneGraphRef.current?.gain;
    if (gain) gain.gain.value = Math.max(0, Math.min(2, voiceSettings.inputVolume / 100));
  }, [voiceSettings.inputVolume]);

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
    if (connected && (cameraTrackRef.current || screenTrackRef.current)) {
      void videoControlRef.current?.applyQuality();
    }
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
    if (localCameraStream) {
      videoControlRef.current?.stopVideo("camera");
    } else {
      void videoControlRef.current?.startVideo("camera");
    }
  }, [localCameraStream]);

  const toggleScreenShare = useCallback(() => {
    if (localScreenStream) {
      videoControlRef.current?.stopVideo("screen");
    } else {
      void videoControlRef.current?.startVideo("screen");
    }
  }, [localScreenStream]);

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
    cameraEnabled: Boolean(localCameraStream),
    screenShareEnabled: Boolean(localScreenStream),
    localCameraStream,
    localScreenStream,
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
