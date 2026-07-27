import { useEffect, useMemo, useRef, useState } from "react";

import type { VoiceChannelState, VoiceParticipant, VideoKind } from "../hooks/useVoiceChannel";
import type { User } from "../types";

interface VideoSource {
  id: string;
  stream: MediaStream;
  label: string;
  muted: boolean;
  mirror: boolean;
  badge: string;
}

interface VideoTileProps extends VideoSource {
  compact?: boolean;
  selected?: boolean;
  onSelect?: () => void;
}

function VideoTile({
  stream,
  label,
  muted,
  mirror,
  badge,
  compact = false,
  selected = false,
  onSelect,
}: VideoTileProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);

  useEffect(() => {
    const el = videoRef.current;
    if (el && el.srcObject !== stream) {
      el.srcObject = stream;
    }
  }, [stream]);

  return (
    <button
      type="button"
      className={[
        "video-tile",
        compact ? "video-tile--compact" : "video-tile--primary",
        selected ? "video-tile--selected" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      onClick={onSelect}
      aria-label={compact ? `${label} görüntüsünü büyüt` : `${label} görüntüsü`}
    >
      <video
        ref={videoRef}
        autoPlay
        playsInline
        muted={muted}
        className={mirror ? "video-tile__video video-tile__video--mirror" : "video-tile__video"}
      />
      <span className="video-tile__label">
        <span className="video-tile__badge">{badge}</span>
        {label}
      </span>
    </button>
  );
}

function hasVideo(stream: MediaStream): boolean {
  return stream.getVideoTracks().some((track) => track.readyState === "live");
}

interface StageControlsProps {
  voice: VoiceChannelState;
  isFullscreen: boolean;
  onToggleFullscreen: () => void;
  onLeave: () => void;
}

function StageControls({ voice, isFullscreen, onToggleFullscreen, onLeave }: StageControlsProps) {
  return (
    <div className="video-stage__controls" aria-label="Görüşme kontrolleri">
      <button
        type="button"
        className={voice.muted ? "stage-control stage-control--danger" : "stage-control"}
        onClick={voice.toggleMute}
        title={voice.muted ? "Mikrofonu aç" : "Mikrofonu kapat"}
      >
        <span className="stage-control__icon" aria-hidden="true">{voice.muted ? "M!" : "MIC"}</span>
        <span>{voice.muted ? "Sesi aç" : "Sustur"}</span>
      </button>
      <button
        type="button"
        className={voice.deafened ? "stage-control stage-control--danger" : "stage-control"}
        onClick={voice.toggleDeafen}
        title={voice.deafened ? "Gelen sesi aç" : "Gelen sesi kapat"}
      >
        <span className="stage-control__icon" aria-hidden="true">AUD</span>
        <span>{voice.deafened ? "Sesi aç" : "Sağırlaştır"}</span>
      </button>
      <button
        type="button"
        className={voice.videoKind === "camera" ? "stage-control stage-control--active" : "stage-control"}
        onClick={voice.toggleCamera}
        title={voice.videoKind === "camera" ? "Kamerayı kapat" : "Kamerayı aç"}
      >
        <span className="stage-control__icon" aria-hidden="true">CAM</span>
        <span>Kamera</span>
      </button>
      <button
        type="button"
        className={voice.videoKind === "screen" ? "stage-control stage-control--active" : "stage-control"}
        onClick={voice.toggleScreenShare}
        title={voice.videoKind === "screen" ? "Ekran paylaşımını durdur" : "Ekran paylaş"}
      >
        <span className="stage-control__icon" aria-hidden="true">SHR</span>
        <span>Paylaş</span>
      </button>
      <span className="video-stage__control-separator" />
      <button
        type="button"
        className="stage-control"
        onClick={onToggleFullscreen}
        title={isFullscreen ? "Tam ekrandan çık" : "Tam ekran"}
      >
        <span className="stage-control__icon stage-control__icon--wide" aria-hidden="true">
          {isFullscreen ? "EXIT" : "FULL"}
        </span>
        <span>{isFullscreen ? "Küçült" : "Tam ekran"}</span>
      </button>
      <button
        type="button"
        className="stage-control stage-control--leave"
        onClick={onLeave}
        title="Ses kanalından ayrıl"
      >
        <span className="stage-control__icon" aria-hidden="true">END</span>
        <span>Ayrıl</span>
      </button>
    </div>
  );
}

interface VideoStageProps {
  currentUser: User;
  participants: VoiceParticipant[];
  localVideoStream: MediaStream | null;
  localVideoKind: VideoKind;
  remoteStreams: Map<number, MediaStream>;
  voice: VoiceChannelState;
  onLeave: () => void;
}

export function VideoStage({
  currentUser,
  participants,
  localVideoStream,
  localVideoKind,
  remoteStreams,
  voice,
  onLeave,
}: VideoStageProps) {
  const stageRef = useRef<HTMLDivElement | null>(null);
  const [focusedId, setFocusedId] = useState<string | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);

  const sources = useMemo<VideoSource[]>(() => {
    const nameOf = (userId: number) =>
      participants.find((participant) => participant.user_id === userId)?.username ?? `#${userId}`;

    const remote: VideoSource[] = Array.from(remoteStreams.entries())
      .filter(([, stream]) => hasVideo(stream))
      .map(([userId, stream]) => ({
        id: `remote-${userId}`,
        stream,
        label: nameOf(userId),
        muted: true,
        mirror: false,
        badge: "LIVE",
      }));

    const local =
      localVideoStream && hasVideo(localVideoStream)
        ? [
            {
              id: "local",
              stream: localVideoStream,
              label: `${currentUser.display_name || currentUser.username} (sen)`,
              muted: true,
              mirror: localVideoKind === "camera",
              badge: localVideoKind === "screen" ? "EKRAN" : "KAMERA",
            } satisfies VideoSource,
          ]
        : [];

    // İzleyici için uzak yayın varsayılan odak, yalnızca kendi yayını varsa yerel görüntü odak olur.
    return [...remote, ...local];
  }, [currentUser.display_name, currentUser.username, localVideoKind, localVideoStream, participants, remoteStreams]);

  const sourceIds = sources.map((source) => source.id).join("|");

  useEffect(() => {
    setFocusedId((current) =>
      current && sources.some((source) => source.id === current) ? current : (sources[0]?.id ?? null),
    );
  }, [sourceIds]);

  useEffect(() => {
    const handleFullscreenChange = () => setIsFullscreen(document.fullscreenElement === stageRef.current);
    document.addEventListener("fullscreenchange", handleFullscreenChange);
    return () => document.removeEventListener("fullscreenchange", handleFullscreenChange);
  }, []);

  if (sources.length === 0) return null;

  const focused = sources.find((source) => source.id === focusedId) ?? sources[0];

  async function toggleFullscreen() {
    const stage = stageRef.current;
    if (!stage) return;
    try {
      if (document.fullscreenElement === stage) {
        await document.exitFullscreen();
      } else {
        await stage.requestFullscreen();
      }
    } catch {
      // Tarayıcı veya kullanıcı tam ekran isteğini engellerse mevcut düzen kullanılmaya devam eder.
    }
  }

  return (
    <div className="video-stage" ref={stageRef}>
      <div className="video-stage__ambient" />
      <div className="video-stage__header">
        <div>
          <span className="video-stage__eyebrow">CANLI SAHNE</span>
          <strong>{focused.label}</strong>
        </div>
        <span className="video-stage__quality">
          <span className="video-stage__live-dot" />
          HD canlı
        </span>
      </div>

      <div className="video-stage__viewport">
        <VideoTile {...focused} />
        {sources.length > 1 ? (
          <div className="video-stage__filmstrip" aria-label="Diğer yayınlar">
            {sources.map((source) => (
              <VideoTile
                key={source.id}
                {...source}
                compact
                selected={source.id === focused.id}
                onSelect={() => setFocusedId(source.id)}
              />
            ))}
          </div>
        ) : null}
      </div>

      <StageControls
        voice={voice}
        isFullscreen={isFullscreen}
        onToggleFullscreen={toggleFullscreen}
        onLeave={onLeave}
      />
    </div>
  );
}
