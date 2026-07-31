import { useCallback, useEffect, useRef, useState } from "react";

import { coreApi, getToken } from "../api/client";
import { webSocketUrl } from "../desktopBridge";
import { VIDEO_QUALITY_PRESETS, buildAudioConstraints } from "../settings";
import type { VoiceSettings } from "../settings";
import { usePushToTalk } from "./usePushToTalk";

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
  audioTransceiver: RTCRtpTransceiver | null;
  cameraTransceiver: RTCRtpTransceiver | null;
  screenTransceiver: RTCRtpTransceiver | null;
  remoteMediaMids: MediaMids;
  remoteWantsScreen: boolean;
}

export interface RemoteVideoStream {
  userId: number;
  kind: "camera" | "screen";
  stream: MediaStream;
}

interface RemoteAudioGraph {
  source: MediaStreamAudioSourceNode;
  gain: GainNode;
  destination: MediaStreamAudioDestinationNode;
}

interface OutgoingAudioGraph {
  context: AudioContext;
  gain: GainNode;
  soundboardGain: GainNode;
  destination: MediaStreamAudioDestinationNode;
  screenDestination: MediaStreamAudioDestinationNode;
  localSoundboardDestination: MediaStreamAudioDestinationNode;
  localSoundboardElement: HTMLAudioElement;
}

export interface VoiceConnectionQuality {
  level: "good" | "fair" | "poor" | "unknown";
  pingMs: number | null;
  packetLossPercent: number | null;
}

interface MediaMids {
  audio: string | null;
  camera: string | null;
  screen: string | null;
}

const SPEAKING_THRESHOLD = 12;
const SIGNALING_TIMEOUT_MS = 6_000;
const ICE_CONFIG_TIMEOUT_MS = 1_600;
const DEFAULT_ICE_SERVERS: RTCIceServer[] = [
  { urls: "stun:stun.cloudflare.com:3478" },
  { urls: "stun:stun.l.google.com:19302" },
];
const REMOTE_VOLUME_STORAGE_KEY = "nexus.remoteVoiceVolumes";

function loadRemoteVolumes(): Map<number, number> {
  try {
    const parsed = JSON.parse(localStorage.getItem(REMOTE_VOLUME_STORAGE_KEY) ?? "{}");
    const entries = Object.entries(parsed)
      .map(([key, value]) => [Number(key), Number(value)] as const)
      .filter(([key, value]) =>
        Number.isInteger(key) && key > 0 && Number.isFinite(value) && value >= 0 && value <= 200,
      );
    return new Map(entries);
  } catch {
    return new Map();
  }
}

function saveRemoteVolumes(volumes: Map<number, number>): void {
  try {
    localStorage.setItem(
      REMOTE_VOLUME_STORAGE_KEY,
      JSON.stringify(Object.fromEntries(volumes)),
    );
  } catch {
    // Gizli mod/depolama kotası sesli görüşmeyi engellememeli.
  }
}

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

async function resumeAudioContext(context: AudioContext | null | undefined): Promise<void> {
  if (!context || context.state === "closed" || context.state === "running") return;
  await context.resume();
}

async function startAudioPlayback(
  context: AudioContext | null | undefined,
  element: HTMLMediaElement,
): Promise<void> {
  await resumeAudioContext(context);
  await element.play();
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
    const frameRateMultiplier = vs.videoFrameRate === 60 ? 1.5 : 1;
    const motionMultiplier = kind === "screen" && vs.screenShareMode === "motion" ? 1.15 : 1;
    const parameters = sender.getParameters();
    if (!parameters.encodings?.length) parameters.encodings = [{}];
    parameters.encodings[0].maxBitrate = Math.round(
      baseBitrate * frameRateMultiplier * motionMultiplier,
    );
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
    parameters.degradationPreference =
      kind === "screen" && vs.screenShareMode === "motion"
        ? "maintain-framerate"
        : "maintain-resolution";
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

function mediaMidsFromSdp(sdp: string | undefined): MediaMids {
  const result: MediaMids = { audio: null, camera: null, screen: null };
  if (!sdp) return result;
  const videoMids: string[] = [];
  for (const section of sdp.split(/\r?\nm=/).slice(1)) {
    const mediaType = section.split(/\s+/, 1)[0];
    const mid = section.match(/(?:^|\r?\n)a=mid:([^\r\n]+)/)?.[1] ?? null;
    if (!mid) continue;
    if (mediaType === "audio" && result.audio === null) result.audio = mid;
    if (mediaType === "video") videoMids.push(mid);
  }
  result.camera = videoMids[0] ?? null;
  result.screen = videoMids[1] ?? null;
  return result;
}

function mediaMidsFromSignal(value: unknown, sdp: string | undefined): MediaMids {
  const fallback = mediaMidsFromSdp(sdp);
  if (!value || typeof value !== "object") return fallback;
  const candidate = value as Record<string, unknown>;
  return {
    audio: typeof candidate.audio === "string" ? candidate.audio : fallback.audio,
    camera: typeof candidate.camera === "string" ? candidate.camera : fallback.camera,
    screen: typeof candidate.screen === "string" ? candidate.screen : fallback.screen,
  };
}

export function useVoiceChannel(channelId: number | null, voiceSettings: VoiceSettings) {
  const [connected, setConnected] = useState(false);
  const [participants, setParticipants] = useState<VoiceParticipant[]>([]);
  const [muted, setMuted] = useState(false);
  const [deafened, setDeafened] = useState(false);
  const [localCameraStream, setLocalCameraStream] = useState<MediaStream | null>(null);
  const [localScreenStream, setLocalScreenStream] = useState<MediaStream | null>(null);
  const [screenAudioEnabled, setScreenAudioEnabled] = useState(false);
  const [remoteStreams, setRemoteStreams] = useState<Map<string, RemoteVideoStream>>(new Map());
  const [ignoredRemoteVideoIds, setIgnoredRemoteVideoIds] = useState<Set<number>>(new Set());
  const [ignoredRemoteScreenIds, setIgnoredRemoteScreenIds] = useState<Set<number>>(new Set());
  const [remoteVolumes, setRemoteVolumes] = useState<Map<number, number>>(loadRemoteVolumes);
  const [soundboardVolume, setSoundboardVolumeState] = useState(100);
  const [soundboardMuted, setSoundboardMuted] = useState(false);
  const [connectionQuality, setConnectionQuality] = useState<VoiceConnectionQuality>({
    level: "unknown",
    pingMs: null,
    packetLossPercent: null,
  });
  const [error, setError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const localStreamRef = useRef<MediaStream | null>(null); // mikrofon + varsa yayın sesi
  const microphoneSourceRef = useRef<MediaStream | null>(null);
  const microphoneGraphRef = useRef<OutgoingAudioGraph | null>(null);
  const audioReplaceRef = useRef<((stream: MediaStream | null) => Promise<void>) | null>(null);
  const soundboardVolumeRef = useRef(soundboardVolume);
  const soundboardMutedRef = useRef(soundboardMuted);
  const cameraTrackRef = useRef<MediaStreamTrack | null>(null);
  const screenTrackRef = useRef<MediaStreamTrack | null>(null);
  const screenAudioStreamRef = useRef<MediaStream | null>(null);
  const placeholderVideoRef = useRef<
    Partial<Record<"camera" | "screen", { canvas: HTMLCanvasElement; track: MediaStreamTrack }>>
  >({});
  const peersRef = useRef<Map<number, PeerState>>(new Map());
  const pendingIceRef = useRef<Map<number, RTCIceCandidateInit[]>>(new Map());
  const audioElsRef = useRef<Map<number, HTMLAudioElement>>(new Map());
  const remoteAudioStreamsRef = useRef<Map<number, MediaStream>>(new Map());
  const remoteAudioContextRef = useRef<AudioContext | null>(null);
  const remoteAudioGraphsRef = useRef<Map<number, RemoteAudioGraph>>(new Map());
  const remoteVolumesRef = useRef(remoteVolumes);
  // Her peer için tek bir birleşik uzak MediaStream. Ses ve video ayrı MSID'lerle gelse de
  // aynı stream'de biriktirilir; böylece video eklenince ses stream'i ezilmez (Hata 1).
  const remoteMediaRef = useRef<Map<string, MediaStream>>(new Map());
  const remoteVideoStateRef = useRef<Map<string, boolean>>(new Map());
  const ignoredRemoteVideoIdsRef = useRef<Set<number>>(new Set());
  const ignoredRemoteScreenIdsRef = useRef<Set<number>>(new Set());
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
  remoteVolumesRef.current = remoteVolumes;
  soundboardVolumeRef.current = soundboardVolume;
  soundboardMutedRef.current = soundboardMuted;

  function disconnectRemoteAudioGraph(peerId: number) {
    const graph = remoteAudioGraphsRef.current.get(peerId);
    if (!graph) return;
    graph.source.disconnect();
    graph.gain.disconnect();
    graph.destination.stream.getTracks().forEach((track) => track.stop());
    remoteAudioGraphsRef.current.delete(peerId);
  }

  function attachRemoteAudio(peerId: number, stream: MediaStream) {
    remoteAudioStreamsRef.current.set(peerId, stream);
    disconnectRemoteAudioGraph(peerId);

    let audioEl = audioElsRef.current.get(peerId);
    if (!audioEl) {
      // Chromium/Electron bazı sürümlerde DOM'a bağlı olmayan `new Audio()` WebRTC
      // stream'ini oynuyor görünüp sessiz kalabiliyor. Görünmez fakat gerçek bir medya
      // elemanı kullan; böylece autoplay ve seçili sink yaşam döngüsü kararlı olsun.
      audioEl = document.createElement("audio");
      audioEl.autoplay = true;
      audioEl.setAttribute("playsinline", "");
      audioEl.setAttribute("aria-hidden", "true");
      audioEl.style.display = "none";
      document.body.appendChild(audioEl);
      audioElsRef.current.set(peerId, audioEl);
    }

    const remoteVolume = remoteVolumesRef.current.get(peerId) ?? 100;
    const outputVolume = Math.max(
      0,
      Math.min(1, voiceSettingsRef.current.outputVolume / 100),
    );
    let playbackContext: AudioContext | null = null;

    if (remoteVolume <= 100) {
      // Normal dinleme yolunda uzak WebRTC stream'ini doğrudan media elementine ver.
      // Stream -> AudioContext -> MediaStreamDestination -> Audio zinciri Chromium'da
      // autoplay/context durumu "running" görünse bile sessiz kalabiliyor. Doğrudan yol,
      // WebRTC'nin tarayıcı tarafından desteklenen doğal oynatma hattıdır.
      audioEl.srcObject = stream;
      audioEl.volume = outputVolume * (remoteVolume / 100);
    } else {
      // HTMLMediaElement volume 1 ile sınırlı olduğu için yalnız %100 üzeri istekte
      // yazılımsal gain kullan. Slider etkileşimi AudioContext'i de kullanıcı hareketiyle
      // uyandırır; normal %0-%100 dinleme bu ek zincire bağımlı değildir.
      let audioContext = remoteAudioContextRef.current;
      if (!audioContext || audioContext.state === "closed") {
        audioContext = new AudioContext();
        remoteAudioContextRef.current = audioContext;
      }
      const source = audioContext.createMediaStreamSource(stream);
      const gain = audioContext.createGain();
      const destination = audioContext.createMediaStreamDestination();
      gain.gain.value = remoteVolume / 100;
      source.connect(gain);
      gain.connect(destination);
      remoteAudioGraphsRef.current.set(peerId, { source, gain, destination });
      audioEl.srcObject = destination.stream;
      audioEl.volume = outputVolume;
      playbackContext = audioContext;
    }

    audioEl.muted = deafenedRef.current;
    void applySinkId(audioEl, voiceSettingsRef.current.outputDeviceId);
    void startAudioPlayback(playbackContext, audioEl).catch(() => {
      setError("Uzak sesi başlatmak için Nexus sayfasına bir kez tıklayın.");
    });
  }

  async function resumeRemoteAudioPlayback(peerId: number): Promise<void> {
    const audioElement = audioElsRef.current.get(peerId);
    if (!audioElement) return;
    const playbackContext = remoteAudioGraphsRef.current.has(peerId)
      ? remoteAudioContextRef.current
      : null;
    await startAudioPlayback(playbackContext, audioElement);
  }

  function resumeAllRemoteAudioPlayback(): void {
    for (const peerId of audioElsRef.current.keys()) {
      void resumeRemoteAudioPlayback(peerId).catch(() => {});
    }
  }

  function placeholderVideoTrack(kind: "camera" | "screen"): MediaStreamTrack {
    const existing = placeholderVideoRef.current[kind];
    if (existing?.track.readyState === "live") return existing.track;
    const canvas = document.createElement("canvas");
    canvas.width = 2;
    canvas.height = 2;
    const track = canvas.captureStream(0).getVideoTracks()[0];
    if (!track) throw new Error("Tarayıcı video yer tutucusu oluşturamadı.");
    placeholderVideoRef.current[kind] = { canvas, track };
    return track;
  }

  const rebuildOutgoingAudioStream = useCallback((
    microphoneStream: MediaStream | null,
    screenStream: MediaStream | null,
    ensureSoundboardOutput = false,
  ): MediaStream | null => {
    const previousGraph = microphoneGraphRef.current;
    if (previousGraph) {
      previousGraph.localSoundboardElement.pause();
      previousGraph.localSoundboardElement.srcObject = null;
      previousGraph.localSoundboardDestination.stream
        .getTracks()
        .forEach((track) => track.stop());
      previousGraph.screenDestination.stream.getTracks().forEach((track) => track.stop());
      void previousGraph.context.close();
    }
    microphoneGraphRef.current = null;
    const hasMicrophone = Boolean(
      microphoneStream?.getAudioTracks().some((track) => track.readyState === "live"),
    );
    const hasScreenAudio = Boolean(
      screenStream?.getAudioTracks().some((track) => track.readyState === "live"),
    );
    if (!hasMicrophone && !hasScreenAudio && !ensureSoundboardOutput) return null;

    const context = new AudioContext();
    const gain = context.createGain();
    const soundboardGain = context.createGain();
    const destination = context.createMediaStreamDestination();
    const screenDestination = context.createMediaStreamDestination();
    const localSoundboardDestination = context.createMediaStreamDestination();
    const localSoundboardElement = new Audio();
    localSoundboardElement.autoplay = true;
    localSoundboardElement.srcObject = localSoundboardDestination.stream;
    localSoundboardElement.volume = Math.max(
      0,
      Math.min(1, voiceSettingsRef.current.outputVolume / 100),
    );
    void applySinkId(localSoundboardElement, voiceSettingsRef.current.outputDeviceId);
    gain.gain.value = mutedRef.current
      ? 0
      : Math.max(0, Math.min(2, voiceSettingsRef.current.inputVolume / 100));

    if (hasMicrophone && microphoneStream) {
      const source = context.createMediaStreamSource(microphoneStream);
      if (voiceSettingsRef.current.noiseSuppression) {
        const highPass = context.createBiquadFilter();
        const compressor = context.createDynamicsCompressor();
        highPass.type = "highpass";
        highPass.frequency.value = 80;
        highPass.Q.value = 0.7;
        compressor.threshold.value = -24;
        compressor.knee.value = 18;
        compressor.ratio.value = 3;
        compressor.attack.value = 0.003;
        compressor.release.value = 0.25;
        source.connect(highPass);
        highPass.connect(compressor);
        compressor.connect(gain);
      } else {
        source.connect(gain);
      }
    }
    gain.connect(destination);
    gain.connect(screenDestination);
    soundboardGain.gain.value = soundboardMutedRef.current || deafenedRef.current
      ? 0
      : Math.max(0, Math.min(2, soundboardVolumeRef.current / 100));
    soundboardGain.connect(destination);
    soundboardGain.connect(screenDestination);
    // Soundboard tek kaynak düğümünden ana konuşma miksine, ekran sesli tam mikse ve yerel
    // hoparlöre gider. Böylece yeni transceiver oluşmaz; ekran aboneliği değişse bile temel
    // soundboard sesi ana WebRTC audio m-line'ında kalır.
    soundboardGain.connect(localSoundboardDestination);

    if (hasScreenAudio && screenStream) {
      const screenSource = context.createMediaStreamSource(screenStream);
      const screenGain = context.createGain();
      screenGain.gain.value = 1;
      screenSource.connect(screenGain);
      screenGain.connect(screenDestination);
    }
    void resumeAudioContext(context).catch(() => {});
    microphoneGraphRef.current = {
      context,
      gain,
      soundboardGain,
      destination,
      screenDestination,
      localSoundboardDestination,
      localSoundboardElement,
    };
    return destination.stream;
  }, []);

  const ensureSoundboardGraph = useCallback(async () => {
    if (deafenedRef.current) {
      throw new Error("Sağırlaştırma açıkken soundboard kullanılamaz.");
    }
    if (!audioReplaceRef.current) {
      throw new Error("Soundboard için önce ses kanalına bağlanın.");
    }
    let graph = microphoneGraphRef.current;
    if (!graph || graph.context.state === "closed") {
      const stream = rebuildOutgoingAudioStream(
        microphoneSourceRef.current,
        screenAudioStreamRef.current,
        true,
      );
      if (!stream) throw new Error("Soundboard ses hattı oluşturulamadı.");
      await audioReplaceRef.current(stream);
      graph = microphoneGraphRef.current;
    }
    if (!graph) throw new Error("Soundboard ses hattı hazır değil.");
    await applySinkId(graph.localSoundboardElement, voiceSettingsRef.current.outputDeviceId);
    try {
      await startAudioPlayback(graph.context, graph.localSoundboardElement);
    } catch {
      throw new Error("Soundboard sesini başlatmak için sayfaya tıklayıp tekrar deneyin.");
    }
    return graph;
  }, [rebuildOutgoingAudioStream]);

  const playSoundboardPreset = useCallback(async (
    preset: "airhorn" | "clap" | "victory" | "fail",
  ) => {
    const graph = await ensureSoundboardGraph();
    const { context, soundboardGain: output } = graph;
    const now = context.currentTime;

    if (preset === "clap") {
      const buffer = context.createBuffer(1, Math.floor(context.sampleRate * 0.34), context.sampleRate);
      const data = buffer.getChannelData(0);
      for (let index = 0; index < data.length; index += 1) {
        const decay = Math.exp(-index / (context.sampleRate * 0.055));
        data[index] = (Math.random() * 2 - 1) * decay * (index % 130 < 72 ? 1 : 0.35);
      }
      const source = context.createBufferSource();
      const highPass = context.createBiquadFilter();
      highPass.type = "highpass";
      highPass.frequency.value = 700;
      source.buffer = buffer;
      source.connect(highPass);
      highPass.connect(output);
      source.start(now);
      return;
    }

    const notes = preset === "victory"
      ? [523.25, 659.25, 783.99, 1046.5]
      : preset === "fail"
        ? [392, 330, 262, 196]
        : [220, 277.18];
    notes.forEach((frequency, index) => {
      const oscillator = context.createOscillator();
      const envelope = context.createGain();
      const start = now + (preset === "airhorn" ? 0 : index * 0.14);
      const duration = preset === "airhorn" ? 0.72 : 0.18;
      oscillator.type = preset === "airhorn" ? "sawtooth" : "square";
      oscillator.frequency.setValueAtTime(frequency, start);
      if (preset === "airhorn") oscillator.frequency.linearRampToValueAtTime(frequency * 1.04, start + duration);
      envelope.gain.setValueAtTime(0.0001, start);
      envelope.gain.exponentialRampToValueAtTime(preset === "airhorn" ? 0.19 : 0.12, start + 0.015);
      envelope.gain.exponentialRampToValueAtTime(0.0001, start + duration);
      oscillator.connect(envelope);
      envelope.connect(output);
      oscillator.start(start);
      oscillator.stop(start + duration + 0.02);
    });
  }, [ensureSoundboardGraph]);

  const playSoundboardClip = useCallback(async (blob: Blob) => {
    const graph = await ensureSoundboardGraph();
    const audioBuffer = await graph.context.decodeAudioData(await blob.arrayBuffer());
    if (audioBuffer.duration > 12) {
      throw new Error("Soundboard sesi en fazla 12 saniye olabilir.");
    }
    const source = graph.context.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(graph.soundboardGain);
    source.start();
  }, [ensureSoundboardGraph]);

  const setSoundboardVolume = useCallback((volume: number) => {
    const normalized = Math.max(0, Math.min(200, Math.round(volume)));
    soundboardVolumeRef.current = normalized;
    setSoundboardVolumeState(normalized);
    const gain = microphoneGraphRef.current?.soundboardGain;
    if (gain) {
      gain.gain.value = soundboardMutedRef.current || deafenedRef.current
        ? 0
        : normalized / 100;
    }
  }, []);

  const toggleSoundboardMute = useCallback(() => {
    const next = !soundboardMutedRef.current;
    soundboardMutedRef.current = next;
    setSoundboardMuted(next);
    const gain = microphoneGraphRef.current?.soundboardGain;
    if (gain) {
      gain.gain.value = next || deafenedRef.current
        ? 0
        : soundboardVolumeRef.current / 100;
    }
  }, []);

  const processMicrophoneStream = useCallback(async (sourceStream: MediaStream) => {
    microphoneSourceRef.current?.getTracks().forEach((track) => track.stop());
    microphoneSourceRef.current = sourceStream;
    const mixed = rebuildOutgoingAudioStream(sourceStream, screenAudioStreamRef.current);
    if (!mixed) throw new Error("Mikrofon ses hattı oluşturulamadı.");
    await resumeAudioContext(microphoneGraphRef.current?.context);
    return mixed;
  }, [rebuildOutgoingAudioStream]);

  const applyMuted = useCallback((nextMuted: boolean) => {
    setMuted(nextMuted);
    mutedRef.current = nextMuted;
    const microphoneGain = microphoneGraphRef.current?.gain;
    if (microphoneGain) {
      microphoneGain.gain.value = nextMuted
        ? 0
        : Math.max(0, Math.min(2, voiceSettingsRef.current.inputVolume / 100));
    }
    localStreamRef.current?.getAudioTracks().forEach((track) => {
      // Birleştirilmiş çıkış açık kalır; mute yalnız mikrofon gain'ini sıfırlar.
      // Böylece ekran sesi ve ayrı soundboard mute'u korunur.
      track.enabled = true;
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
      const soundboardGain = microphoneGraphRef.current?.soundboardGain;
      if (soundboardGain) {
        soundboardGain.gain.value = nextDeafened || soundboardMutedRef.current
          ? 0
          : soundboardVolumeRef.current / 100;
      }
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

  const setRemoteVolume = useCallback((peerId: number, volume: number) => {
    const normalized = Math.max(0, Math.min(200, Math.round(volume)));
    const next = new Map(remoteVolumesRef.current);
    if (normalized === 100) next.delete(peerId);
    else next.set(peerId, normalized);
    remoteVolumesRef.current = next;
    setRemoteVolumes(next);
    saveRemoteVolumes(next);
    const graph = remoteAudioGraphsRef.current.get(peerId);
    if (graph && normalized > 100) {
      graph.gain.gain.value = normalized / 100;
      return;
    }
    const stream = remoteAudioStreamsRef.current.get(peerId);
    if (stream) attachRemoteAudio(peerId, stream);
  }, []);

  const setRemoteVideoEnabled = useCallback((
    peerId: number,
    kind: "camera" | "screen",
    enabled: boolean,
  ) => {
    const ignoredRef =
      kind === "screen" ? ignoredRemoteScreenIdsRef : ignoredRemoteVideoIdsRef;
    const next = new Set(ignoredRef.current);
    if (enabled) next.delete(peerId);
    else next.add(peerId);
    ignoredRef.current = next;
    if (kind === "screen") setIgnoredRemoteScreenIds(next);
    else setIgnoredRemoteVideoIds(next);

    const stream = remoteMediaRef.current.get(`${peerId}:${kind}`);
    stream?.getVideoTracks().forEach((track) => {
      track.enabled = enabled;
    });

    // DOM'da gizlemek trafik tasarrufu sağlamaz. İlgili receiver yönünü kapatıp yeniden
    // pazarlık yapınca yayıncı bu kullanıcı için video encode/gönderimini durdurur.
    const peer = peersRef.current.get(peerId);
    const transceiver =
      kind === "screen" ? peer?.screenTransceiver : peer?.cameraTransceiver;
    const localTrack = kind === "screen" ? screenTrackRef.current : cameraTrackRef.current;
    if (peer && transceiver) {
      const nextDirection = videoDirection(Boolean(localTrack), enabled);
      if (transceiver.direction !== nextDirection) {
        transceiver.direction = nextDirection;
        peer.requestNegotiation();
      }
    }

    if (kind === "screen") {
      // Yayın sesi mikrofon/soundboard ile aynı audio m-line'ında kalır. Yayıncı bu tercih
      // sinyalini alınca yalnız bu peer'in sender'ını yayın sesi içermeyen mikse geçirir.
      sendWebSocketJson(wsRef.current, {
        type: "media-subscription",
        to: peerId,
        kind: "screen",
        enabled,
      });
    }
  }, []);

  const toggleRemoteVideo = useCallback(
    (peerId: number, kind: "camera" | "screen") => {
      const ignored =
        kind === "screen" ? ignoredRemoteScreenIdsRef.current : ignoredRemoteVideoIdsRef.current;
      setRemoteVideoEnabled(peerId, kind, ignored.has(peerId));
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
      el.pause();
      el.srcObject = null;
      el.remove();
    });
    audioElsRef.current.clear();
    remoteAudioGraphsRef.current.forEach((graph) => {
      graph.source.disconnect();
      graph.gain.disconnect();
      graph.destination.stream.getTracks().forEach((track) => track.stop());
    });
    remoteAudioGraphsRef.current.clear();
    remoteAudioStreamsRef.current.clear();
    void remoteAudioContextRef.current?.close();
    remoteAudioContextRef.current = null;
    remoteMediaRef.current.clear();
    remoteVideoStateRef.current.clear();
    localStreamRef.current?.getTracks().forEach((track) => track.stop());
    localStreamRef.current = null;
    microphoneSourceRef.current?.getTracks().forEach((track) => track.stop());
    microphoneSourceRef.current = null;
    const outgoingGraph = microphoneGraphRef.current;
    if (outgoingGraph) {
      outgoingGraph.localSoundboardElement.pause();
      outgoingGraph.localSoundboardElement.srcObject = null;
      outgoingGraph.localSoundboardDestination.stream
        .getTracks()
        .forEach((track) => track.stop());
      outgoingGraph.screenDestination.stream.getTracks().forEach((track) => track.stop());
      void outgoingGraph.context.close();
    }
    microphoneGraphRef.current = null;
    cameraTrackRef.current?.stop();
    screenTrackRef.current?.stop();
    screenAudioStreamRef.current?.getTracks().forEach((track) => track.stop());
    cameraTrackRef.current = null;
    screenTrackRef.current = null;
    screenAudioStreamRef.current = null;
    Object.values(placeholderVideoRef.current).forEach((source) => source?.track.stop());
    placeholderVideoRef.current = {};
    setConnected(false);
    setParticipants([]);
    setMuted(false);
    setDeafened(false);
    setLocalCameraStream(null);
    setLocalScreenStream(null);
    setScreenAudioEnabled(false);
    setRemoteStreams(new Map());
    ignoredRemoteVideoIdsRef.current = new Set();
    setIgnoredRemoteVideoIds(new Set());
    ignoredRemoteScreenIdsRef.current = new Set();
    setIgnoredRemoteScreenIds(new Set());
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

    function dropRemoteStream(peerId: number, kind?: "camera" | "screen") {
      setRemoteStreams((prev) => {
        const next = new Map(
          [...prev].filter(([, value]) =>
            value.userId !== peerId || (kind !== undefined && value.kind !== kind),
          ),
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
      if (audioElement) {
        audioElement.pause();
        audioElement.srcObject = null;
        audioElement.remove();
      }
      audioElsRef.current.delete(peerId);
      const audioGraph = remoteAudioGraphsRef.current.get(peerId);
      if (audioGraph) {
        audioGraph.source.disconnect();
        audioGraph.gain.disconnect();
        audioGraph.destination.stream.getTracks().forEach((track) => track.stop());
      }
      remoteAudioGraphsRef.current.delete(peerId);
      remoteAudioStreamsRef.current.delete(peerId);
      for (const key of [...remoteMediaRef.current.keys()]) {
        if (key.startsWith(`${peerId}:`)) remoteMediaRef.current.delete(key);
      }
      for (const key of [...remoteVideoStateRef.current.keys()]) {
        if (key.startsWith(`${peerId}:`)) remoteVideoStateRef.current.delete(key);
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
        element.pause();
        element.srcObject = null;
        element.remove();
      });
      audioElsRef.current.clear();
      remoteAudioGraphsRef.current.forEach((graph) => {
        graph.source.disconnect();
        graph.gain.disconnect();
        graph.destination.stream.getTracks().forEach((track) => track.stop());
      });
      remoteAudioGraphsRef.current.clear();
      remoteAudioStreamsRef.current.clear();
      remoteMediaRef.current.clear();
      remoteVideoStateRef.current.clear();
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
      // Yalnız ilk offer'ı üreten taraf m-line'ları oluşturur. Cevaplayan taraf bunları
      // setRemoteDescription sonrasında bağlar; iki tarafta önceden transceiver oluşturmak
      // Chromium'un ikinci bir audio/video seti eklemesine ve track'lerin yanlış sender'da
      // kalmasına neden olur.
      let audioTransceiver: RTCRtpTransceiver | null = null;
      let cameraTransceiver: RTCRtpTransceiver | null = null;
      let screenTransceiver: RTCRtpTransceiver | null = null;
      if (initiateNegotiation) {
        const audioTrack = localStreamRef.current?.getAudioTracks()[0] ?? null;
        audioTransceiver = pc.addTransceiver(audioTrack ?? "audio", {
          direction: audioTrack ? "sendrecv" : "recvonly",
        });
        const receivingCamera = !ignoredRemoteVideoIdsRef.current.has(peerId);
        const receivingScreen = !ignoredRemoteScreenIdsRef.current.has(peerId);
        cameraTransceiver = pc.addTransceiver(
          cameraTrackRef.current ?? placeholderVideoTrack("camera"),
          { direction: videoDirection(Boolean(cameraTrackRef.current), receivingCamera) },
        );
        screenTransceiver = pc.addTransceiver(
          screenTrackRef.current ?? placeholderVideoTrack("screen"),
          { direction: videoDirection(Boolean(screenTrackRef.current), receivingScreen) },
        );
      }
      const peer: PeerState = {
        pc,
        makingOffer: false,
        ignoreOffer: false,
        polite: selfId > peerId,
        negotiationEnabled: initiateNegotiation,
        negotiationPending: false,
        requestNegotiation: () => {},
        audioTransceiver,
        cameraTransceiver,
        screenTransceiver,
        remoteMediaMids: { audio: null, camera: null, screen: null },
        remoteWantsScreen: true,
      };
      peersRef.current.set(peerId, peer);

      if (cameraTrackRef.current && cameraTransceiver) {
        void optimizeVideoSender(
          cameraTransceiver.sender,
          "camera",
          voiceSettingsRef.current,
        );
      }
      if (screenTrackRef.current && screenTransceiver) {
        void optimizeVideoSender(screenTransceiver.sender, "screen", voiceSettingsRef.current);
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
          sendWebSocketJson(ws, {
            type: "offer",
            to: peerId,
            sdp: pc.localDescription?.sdp,
            media_mids: {
              audio: peer.audioTransceiver?.mid ?? null,
              camera: peer.cameraTransceiver?.mid ?? null,
              screen: peer.screenTransceiver?.mid ?? null,
            },
          });
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
        const isCamera =
          event.transceiver === peer.cameraTransceiver ||
          (peer.remoteMediaMids.camera !== null &&
            event.transceiver.mid === peer.remoteMediaMids.camera);
        const isScreen =
          event.transceiver === peer.screenTransceiver ||
          (peer.remoteMediaMids.screen !== null &&
            event.transceiver.mid === peer.remoteMediaMids.screen);
        if (event.track.kind === "audio") {
          const stream = event.streams[0] ?? new MediaStream([event.track]);
          attachRemoteAudio(peerId, stream);
          // Bazı Chromium sürümlerinde track ilk geldiğinde muted olur ve ilk play() denemesi
          // kalıcı biçimde beklemede kalabilir. Gerçek RTP akışı başladığı anda mevcut audio
          // elemanını tekrar çalıştır; yeni bir katılımcının gelmesine bağımlı kalma.
          event.track.addEventListener("unmute", () => {
            void resumeRemoteAudioPlayback(peerId).catch(() => {});
          });
          return;
        }
        if (!isCamera && !isScreen) return;
        const kind = isScreen ? "screen" : "camera";
        const key = `${peerId}:${kind}`;
        const stream = new MediaStream([event.track]);
        remoteMediaRef.current.set(key, stream);
        const ignored =
          kind === "screen"
            ? ignoredRemoteScreenIdsRef.current.has(peerId)
            : ignoredRemoteVideoIdsRef.current.has(peerId);
        event.track.enabled = !ignored;
        // Güncellenmemiş bir istemci video-state göndermese de önceki WebRTC davranışı çalışsın.
        // Güncel istemcilerde explicit false bu geçici akışı hemen kaldırır.
        if (remoteVideoStateRef.current.get(key) !== false) {
          upsertRemoteStream(peerId, kind, stream);
        }

        // Track susunca/bitince (ör. karşı taraf kamerayı kapatınca) döşemeyi güncelle/kaldır.
        const refresh = () => {
          if (event.track.readyState === "ended") {
            remoteMediaRef.current.delete(key);
            remoteVideoStateRef.current.set(key, false);
            dropRemoteStream(peerId, kind);
            return;
          }
          if (remoteVideoStateRef.current.get(key) !== false) {
            upsertRemoteStream(peerId, kind, stream);
          }
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
          // SDP kurulurken AudioContext askıya alınmış veya sender eski miks track'inde kalmış
          // olabilir. Bağlantı tamamlanınca aynı m-line üzerindeki güncel miksle eşitle.
          void resumeAudioContext(microphoneGraphRef.current?.context).catch(() => {});
          void syncOutgoingAudioSender(peerId, peer).catch(() => {});
          void resumeRemoteAudioPlayback(peerId).catch(() => {});
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

    function outgoingAudioTrackForPeer(
      peer: PeerState,
      voiceStream = localStreamRef.current,
    ): MediaStreamTrack | null {
      const hasScreenAudio = Boolean(
        screenAudioStreamRef.current
          ?.getAudioTracks()
          .some((track) => track.readyState === "live"),
      );
      if (peer.remoteWantsScreen && hasScreenAudio) {
        return microphoneGraphRef.current?.screenDestination.stream.getAudioTracks()[0] ?? null;
      }
      // Mikrofon + soundboard her zaman ana, daha önce çalışan track'te kalır. Yayını
      // izlemeyen kullanıcı temel konuşma için ikincil bir MediaStreamDestination'a bağımlı olmaz.
      return voiceStream?.getAudioTracks()[0] ?? null;
    }

    async function syncOutgoingAudioSender(peerId: number, peer: PeerState): Promise<void> {
      if (peersRef.current.get(peerId) !== peer) return;
      const transceiver = peer.audioTransceiver;
      if (!transceiver) return;
      await resumeAudioContext(microphoneGraphRef.current?.context).catch(() => {});
      const nextTrack = outgoingAudioTrackForPeer(peer);
      if (nextTrack) nextTrack.enabled = true;
      if (transceiver.sender.track !== nextTrack) {
        await transceiver.sender.replaceTrack(nextTrack);
      }
      const nextDirection: RTCRtpTransceiverDirection = nextTrack ? "sendrecv" : "recvonly";
      if (transceiver.direction !== nextDirection) {
        transceiver.direction = nextDirection;
        peer.requestNegotiation();
      }
    }

    async function bindResponderMedia(peerId: number, peer: PeerState) {
      const transceivers = peer.pc.getTransceivers();
      const findByMid = (mid: string | null, kind: "audio" | "video") =>
        transceivers.find(
          (transceiver) =>
            transceiver.mid === mid && transceiver.receiver.track.kind === kind,
        ) ?? null;
      const videoTransceivers = transceivers.filter(
        (transceiver) => transceiver.receiver.track.kind === "video",
      );
      peer.audioTransceiver =
        findByMid(peer.remoteMediaMids.audio, "audio") ??
        transceivers.find((transceiver) => transceiver.receiver.track.kind === "audio") ??
        null;
      peer.cameraTransceiver =
        findByMid(peer.remoteMediaMids.camera, "video") ??
        videoTransceivers[0] ??
        null;
      peer.screenTransceiver =
        findByMid(peer.remoteMediaMids.screen, "video") ??
        videoTransceivers[1] ??
        null;

      const audioTrack = outgoingAudioTrackForPeer(peer);
      if (peer.audioTransceiver) {
        await peer.audioTransceiver.sender.replaceTrack(audioTrack);
        peer.audioTransceiver.direction = audioTrack ? "sendrecv" : "recvonly";
      }

      const localVideo = [
        [
          "camera",
          peer.cameraTransceiver,
          cameraTrackRef.current,
          !ignoredRemoteVideoIdsRef.current.has(peerId),
        ],
        [
          "screen",
          peer.screenTransceiver,
          screenTrackRef.current,
          !ignoredRemoteScreenIdsRef.current.has(peerId),
        ],
      ] as const;
      for (const [kind, transceiver, localTrack, receivingVideo] of localVideo) {
        if (!transceiver) continue;
        await transceiver.sender.replaceTrack(
          localTrack ?? placeholderVideoTrack(kind),
        );
        transceiver.direction = videoDirection(Boolean(localTrack), receivingVideo);
        if (localTrack) {
          await optimizeVideoSender(transceiver.sender, kind, voiceSettingsRef.current);
        }
      }
    }

    async function replaceOutgoingAudioStream(nextStream: MediaStream | null) {
      for (const [, peer] of peersRef.current) {
        const transceiver = peer.audioTransceiver;
        if (!transceiver) continue;
        const nextTrack = outgoingAudioTrackForPeer(peer, nextStream);
        if (nextTrack) nextTrack.enabled = true;
        await transceiver.sender.replaceTrack(nextTrack);
        const nextDirection: RTCRtpTransceiverDirection = nextTrack ? "sendrecv" : "recvonly";
        if (transceiver.direction !== nextDirection) {
          transceiver.direction = nextDirection;
          peer.requestNegotiation();
        }
      }
      localStreamRef.current?.getAudioTracks().forEach((track) => track.stop());
      localStreamRef.current = nextStream;
      setMicEpoch((epoch) => epoch + 1);
    }

    async function applyPeerScreenSubscription(peerId: number, enabled: boolean) {
      const peer = peersRef.current.get(peerId);
      if (!peer) return;
      peer.remoteWantsScreen = enabled;
      const transceiver = peer.audioTransceiver;
      if (!transceiver) return;
      const nextTrack = outgoingAudioTrackForPeer(peer);
      if (nextTrack) nextTrack.enabled = true;
      await transceiver.sender.replaceTrack(nextTrack);
      const nextDirection: RTCRtpTransceiverDirection = nextTrack ? "sendrecv" : "recvonly";
      if (transceiver.direction !== nextDirection) {
        transceiver.direction = nextDirection;
        peer.requestNegotiation();
      }
    }
    audioReplaceRef.current = replaceOutgoingAudioStream;

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
            const microphoneGain = microphoneGraphRef.current?.gain;
            if (microphoneGain) microphoneGain.gain.value = 0;
            setMuted(true);
            mutedRef.current = true;
          }
        } catch (err) {
          microphoneError = `${microphoneErrorMessage(err)} (yalnız dinleyici olarak katılıyorsunuz)`;
          setError(microphoneError);
        }
      }
      // Reconnect aynı işlenmiş track'i yeniden kullanır. Sekme arka planda kaldıysa
      // tarayıcının susturduğu mikseri yeni offer üretilmeden önce tekrar çalıştır.
      await resumeAudioContext(microphoneGraphRef.current?.context).catch(() => {});

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
              sendWebSocketJson(ws, {
                type: "video-state",
                to: peer.user_id,
                kind: "camera",
                enabled: Boolean(cameraTrackRef.current),
              });
              sendWebSocketJson(ws, {
                type: "video-state",
                to: peer.user_id,
                kind: "screen",
                enabled: Boolean(screenTrackRef.current),
              });
              sendWebSocketJson(ws, {
                type: "media-subscription",
                to: peer.user_id,
                kind: "screen",
                enabled: !ignoredRemoteScreenIdsRef.current.has(peer.user_id),
              });
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
            sendWebSocketJson(ws, {
              type: "video-state",
              to: joinedUserId,
              kind: "camera",
              enabled: Boolean(cameraTrackRef.current),
            });
            sendWebSocketJson(ws, {
              type: "video-state",
              to: joinedUserId,
              kind: "screen",
              enabled: Boolean(screenTrackRef.current),
            });
            sendWebSocketJson(ws, {
              type: "media-subscription",
              to: joinedUserId,
              kind: "screen",
              enabled: !ignoredRemoteScreenIdsRef.current.has(joinedUserId),
            });
            // Oda değişimi mevcut Chromium medya oynatımını hareketlendirebiliyor. Bunu tesadüfi
            // tarayıcı davranışına bırakma; mevcut tüm uzak audio elemanlarını açıkça doğrula.
            resumeAllRemoteAudioPlayback();
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
            peer.remoteMediaMids = mediaMidsFromSignal(data.media_mids, description.sdp);
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
            if (
              !peer.audioTransceiver ||
              !peer.cameraTransceiver ||
              !peer.screenTransceiver
            ) {
              await bindResponderMedia(fromId, peer);
            }
            await flushPendingIce(fromId, pc);
            await pc.setLocalDescription();
            sendWebSocketJson(ws, {
              type: "answer",
              to: fromId,
              sdp: pc.localDescription?.sdp,
              media_mids: {
                audio: peer.audioTransceiver?.mid ?? null,
                camera: peer.cameraTransceiver?.mid ?? null,
                screen: peer.screenTransceiver?.mid ?? null,
              },
            });
            peer.negotiationEnabled = true;
            peer.negotiationPending = false;
            await syncOutgoingAudioSender(fromId, peer);
            void resumeRemoteAudioPlayback(fromId).catch(() => {});
            break;
          }
          case "answer": {
            const peer = peersRef.current.get(data.from as number);
            if (peer && peer.pc.signalingState === "have-local-offer") {
              peer.remoteMediaMids = mediaMidsFromSignal(
                data.media_mids,
                data.sdp as string,
              );
              await peer.pc.setRemoteDescription({ type: "answer", sdp: data.sdp as string });
              await flushPendingIce(data.from as number, peer.pc);
              peer.negotiationEnabled = true;
              await syncOutgoingAudioSender(data.from as number, peer);
              void resumeRemoteAudioPlayback(data.from as number).catch(() => {});
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
          case "video-state": {
            const peerId = data.from as number;
            const kind = data.kind === "screen" ? "screen" : "camera";
            const enabled = data.enabled === true;
            const key = `${peerId}:${kind}`;
            remoteVideoStateRef.current.set(key, enabled);
            if (!enabled) {
              dropRemoteStream(peerId, kind);
            } else {
              const stream = remoteMediaRef.current.get(key);
              if (stream) upsertRemoteStream(peerId, kind, stream);
            }
            break;
          }
          case "media-subscription": {
            if (data.kind === "screen" && typeof data.enabled === "boolean") {
              await applyPeerScreenSubscription(data.from as number, data.enabled);
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
        if (event.code === 4409) {
          // Eski sekmenin otomatik reconnect ile yeni cihazı tekrar devirmesini önle. Aynı hesap
          // için en son katılan ses oturumu tek yetkili signaling bağlantısıdır.
          setError("Bu hesap başka bir sekme veya cihazda ses kanalına katıldı; bu oturum kapatıldı.");
          return;
        }
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
                // Chrome/Edge'de kullanıcı paylaşım penceresindeki "sekme/sistem sesini paylaş"
                // seçeneğini açarsa ses aynı WebRTC audio hattına güvenle karıştırılır.
                audio: true,
              });
        const track = stream.getVideoTracks()[0];
        if (!track) return;

        track.contentHint =
          kind === "screen" ? currentSettings.screenShareMode : "motion";
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
        else {
          setLocalScreenStream(stream);
          screenAudioStreamRef.current?.getTracks().forEach((audioTrack) => audioTrack.stop());
          const sharedAudioTracks = stream.getAudioTracks();
          screenAudioStreamRef.current = sharedAudioTracks.length
            ? new MediaStream(sharedAudioTracks)
            : null;
          setScreenAudioEnabled(sharedAudioTracks.length > 0);
          for (const sharedAudioTrack of sharedAudioTracks) {
            sharedAudioTrack.onended = () => {
              const activeAudioStream = screenAudioStreamRef.current;
              if (!activeAudioStream?.getAudioTracks().includes(sharedAudioTrack)) return;
              const remainingTracks = activeAudioStream
                .getAudioTracks()
                .filter((audioTrack) =>
                  audioTrack !== sharedAudioTrack && audioTrack.readyState === "live"
                );
              screenAudioStreamRef.current = remainingTracks.length
                ? new MediaStream(remainingTracks)
                : null;
              setScreenAudioEnabled(remainingTracks.length > 0);
              try {
                const mixedAudio = rebuildOutgoingAudioStream(
                  microphoneSourceRef.current,
                  screenAudioStreamRef.current,
                );
                void resumeAudioContext(microphoneGraphRef.current?.context);
                void replaceOutgoingAudioStream(mixedAudio);
              } catch {
                void replaceOutgoingAudioStream(null);
              }
            };
          }
          try {
            const mixedAudio = rebuildOutgoingAudioStream(
              microphoneSourceRef.current,
              screenAudioStreamRef.current,
            );
            await resumeAudioContext(microphoneGraphRef.current?.context);
            await replaceOutgoingAudioStream(mixedAudio);
          } catch {
            screenAudioStreamRef.current?.getTracks().forEach((audioTrack) => audioTrack.stop());
            screenAudioStreamRef.current = null;
            setScreenAudioEnabled(false);
            const microphoneOnly = rebuildOutgoingAudioStream(
              microphoneSourceRef.current,
              null,
            );
            await resumeAudioContext(microphoneGraphRef.current?.context);
            await replaceOutgoingAudioStream(microphoneOnly);
          }
        }

        // Kullanıcı tarayıcı arayüzünden paylaşımı durdurursa temizle.
        track.onended = () => stopVideo(kind);

        for (const [peerId, peer] of peersRef.current) {
          const transceiver = kind === "camera" ? peer.cameraTransceiver : peer.screenTransceiver;
          if (transceiver) {
            await transceiver.sender.replaceTrack(track);
            const nextDirection = videoDirection(
              true,
              kind === "screen"
                ? !ignoredRemoteScreenIdsRef.current.has(peerId)
                : !ignoredRemoteVideoIdsRef.current.has(peerId),
            );
            const directionChanged = transceiver.direction !== nextDirection;
            if (directionChanged) transceiver.direction = nextDirection;
            await optimizeVideoSender(transceiver.sender, kind, currentSettings);
            // Normal akışta m-line zaten sendrecv'dir; replaceTrack tek başına yayını başlatır.
            // Kullanıcı bu eşin videosunu özellikle kapattıysa sendonly'ye geçiş SDP gerektirir.
            if (directionChanged) peer.requestNegotiation();
          }
          sendWebSocketJson(wsRef.current, {
            type: "video-state",
            to: peerId,
            kind,
            enabled: true,
          });
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
        track.contentHint = kind === "screen" ? currentSettings.screenShareMode : "motion";
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
          const transceiver =
            kind === "camera" ? peer.cameraTransceiver : peer.screenTransceiver;
          if (transceiver) {
            await optimizeVideoSender(transceiver.sender, kind, currentSettings);
          }
        }
      }
    }

    function stopVideo(kind: "camera" | "screen") {
      const trackRef = kind === "camera" ? cameraTrackRef : screenTrackRef;
      const track = trackRef.current;
      trackRef.current = null;
      track?.stop();
      if (kind === "camera") setLocalCameraStream(null);
      else {
        setLocalScreenStream(null);
        screenAudioStreamRef.current?.getTracks().forEach((audioTrack) => audioTrack.stop());
        screenAudioStreamRef.current = null;
        setScreenAudioEnabled(false);
        try {
          const mixedAudio = rebuildOutgoingAudioStream(
            microphoneSourceRef.current,
            null,
          );
          void resumeAudioContext(microphoneGraphRef.current?.context);
          void replaceOutgoingAudioStream(mixedAudio);
        } catch {
          void replaceOutgoingAudioStream(null);
        }
      }
      for (const [peerId, peer] of peersRef.current) {
        const transceiver = kind === "camera" ? peer.cameraTransceiver : peer.screenTransceiver;
        if (transceiver) {
          // İlk SDP'deki yer tutucu ontrack/MSID'yi hazırladığı için burada null'a dönmek
          // güvenlidir; sonraki gerçek track aynı m-line'da devam eder.
          void transceiver.sender.replaceTrack(null);
          const nextDirection = videoDirection(
            false,
            kind === "screen"
              ? !ignoredRemoteScreenIdsRef.current.has(peerId)
              : !ignoredRemoteVideoIdsRef.current.has(peerId),
          );
          const directionChanged = transceiver.direction !== nextDirection;
          if (directionChanged) {
            transceiver.direction = nextDirection;
            peer.requestNegotiation();
          }
        }
        sendWebSocketJson(wsRef.current, {
          type: "video-state",
          to: peerId,
          kind,
          enabled: false,
        });
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
        await replaceOutgoingAudioStream(processedStream);
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
      audioReplaceRef.current = null;
      cleanup();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [channelId]);

  // Konuşma tespiti: yerel mikrofon seviyesini izler, eşiği geçince "speaking" bildirir.
  useEffect(() => {
    if (!connected || !microphoneSourceRef.current) return;

    const audioContext = new AudioContext();
    // Yayın sesi konuşma halkasını tetiklemesin; yalnızca ham mikrofon kaynağını ölç.
    const source = audioContext.createMediaStreamSource(microphoneSourceRef.current);
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

  useEffect(() => {
    if (!connected) {
      setConnectionQuality({ level: "unknown", pingMs: null, packetLossPercent: null });
      return;
    }
    const previousCounters = new Map<string, { received: number; lost: number }>();
    let cancelled = false;

    async function sampleConnectionQuality() {
      const rtts: number[] = [];
      let receivedDelta = 0;
      let lostDelta = 0;
      for (const [peerId, peer] of peersRef.current) {
        let stats: RTCStatsReport;
        try {
          stats = await peer.pc.getStats();
        } catch {
          continue;
        }
        stats.forEach((report) => {
          if (
            report.type === "candidate-pair" &&
            report.state === "succeeded" &&
            typeof report.currentRoundTripTime === "number"
          ) {
            rtts.push(report.currentRoundTripTime * 1000);
          }
          if (
            report.type === "inbound-rtp" &&
            typeof report.packetsReceived === "number" &&
            typeof report.packetsLost === "number"
          ) {
            const key = `${peerId}:${report.id}`;
            const previous = previousCounters.get(key);
            if (previous) {
              receivedDelta += Math.max(0, report.packetsReceived - previous.received);
              lostDelta += Math.max(0, report.packetsLost - previous.lost);
            }
            previousCounters.set(key, {
              received: report.packetsReceived,
              lost: report.packetsLost,
            });
          }
        });
      }
      if (cancelled) return;
      const pingMs = rtts.length
        ? Math.round(rtts.reduce((sum, value) => sum + value, 0) / rtts.length)
        : null;
      const packetTotal = receivedDelta + lostDelta;
      const packetLossPercent = packetTotal > 0
        ? Math.round((lostDelta / packetTotal) * 1000) / 10
        : null;
      const level: VoiceConnectionQuality["level"] =
        pingMs === null && packetLossPercent === null
          ? "unknown"
          : (pingMs ?? 0) < 120 && (packetLossPercent ?? 0) < 2
            ? "good"
            : (pingMs ?? 0) < 250 && (packetLossPercent ?? 0) < 6
              ? "fair"
              : "poor";
      setConnectionQuality({ level, pingMs, packetLossPercent });
    }

    void sampleConnectionQuality();
    const timer = window.setInterval(() => void sampleConnectionQuality(), 5_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [connected]);

  // Tarayıcı güç tasarrufu veya autoplay politikası AudioContext/HTMLAudioElement
  // çıkışlarını askıya alabilir. Sonraki gerçek kullanıcı etkileşiminde mevcut
  // mikrofon mikserini, soundboard monitörünü ve uzak sesleri tekrar uyandır.
  useEffect(() => {
    function resumeActiveAudio() {
      if (document.hidden) return;
      const outgoingGraph = microphoneGraphRef.current;
      const tasks: Promise<void>[] = [];
      if (outgoingGraph) {
        tasks.push(
          startAudioPlayback(
            outgoingGraph.context,
            outgoingGraph.localSoundboardElement,
          ),
        );
      }
      for (const [peerId] of audioElsRef.current) {
        tasks.push(resumeRemoteAudioPlayback(peerId));
      }
      if (tasks.length === 0) return;
      void Promise.all(tasks)
        .then(() => {
          setError((current) =>
            current === "Uzak sesi başlatmak için Nexus sayfasına bir kez tıklayın."
              ? null
              : current,
          );
        })
        .catch(() => {});
    }

    document.addEventListener("pointerdown", resumeActiveAudio);
    document.addEventListener("keydown", resumeActiveAudio);
    document.addEventListener("visibilitychange", resumeActiveAudio);
    return () => {
      document.removeEventListener("pointerdown", resumeActiveAudio);
      document.removeEventListener("keydown", resumeActiveAudio);
      document.removeEventListener("visibilitychange", resumeActiveAudio);
    };
  }, []);

  // Uzak track, connectionState=connected ve ilk `play()` denemesi farklı sıralarda
  // tamamlanabiliyor. Üçüncü bir katılımcının `peer-joined` olayı gelmeden de aynı
  // yeniden-doğrulamayı yap; zaten çalan elemana play() çağrısı zararsızdır.
  useEffect(() => {
    if (!connected) return;
    function keepAudioPathsAlive() {
      if (document.hidden) return;
      void resumeAudioContext(microphoneGraphRef.current?.context).catch(() => {});
      resumeAllRemoteAudioPlayback();
    }
    keepAudioPathsAlive();
    const timer = window.setInterval(keepAudioPathsAlive, 3_000);
    return () => window.clearInterval(timer);
  }, [connected]);

  // Çıkış cihazı (hoparlör) değişince mevcut uzak ses elemanlarına uygula.
  useEffect(() => {
    audioElsRef.current.forEach((el, peerId) => {
      const remoteVolume = remoteVolumesRef.current.get(peerId) ?? 100;
      const combinedVolume = remoteAudioGraphsRef.current.has(peerId)
        ? voiceSettings.outputVolume / 100
        : (voiceSettings.outputVolume / 100) * (remoteVolume / 100);
      el.volume = Math.max(0, Math.min(1, combinedVolume));
      void applySinkId(el, voiceSettings.outputDeviceId);
    });
    const localSoundboardElement = microphoneGraphRef.current?.localSoundboardElement;
    if (localSoundboardElement) {
      localSoundboardElement.volume = Math.max(
        0,
        Math.min(1, voiceSettings.outputVolume / 100),
      );
      void applySinkId(localSoundboardElement, voiceSettings.outputDeviceId);
    }
  }, [voiceSettings.outputDeviceId, voiceSettings.outputVolume]);

  useEffect(() => {
    const gain = microphoneGraphRef.current?.gain;
    if (gain) {
      gain.gain.value = mutedRef.current
        ? 0
        : Math.max(0, Math.min(2, voiceSettings.inputVolume / 100));
    }
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
  }, [
    connected,
    voiceSettings.screenShareMode,
    voiceSettings.videoFrameRate,
    voiceSettings.videoQuality,
  ]);

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
    screenAudioEnabled,
    localCameraStream,
    localScreenStream,
    remoteStreams,
    ignoredRemoteVideoIds,
    ignoredRemoteScreenIds,
    remoteVolumes,
    soundboardVolume,
    soundboardMuted,
    connectionQuality,
    error,
    toggleMute,
    toggleDeafen,
    toggleCamera,
    toggleScreenShare,
    toggleRemoteVideo,
    setRemoteVolume,
    playSoundboardPreset,
    playSoundboardClip,
    setSoundboardVolume,
    toggleSoundboardMute,
    disconnect: cleanup,
  };
}

export type VoiceChannelState = ReturnType<typeof useVoiceChannel>;
