import { useEffect, useMemo, useRef, useState } from "react";

import type { RemoteVideoStream, VoiceChannelState, VoiceParticipant } from "../hooks/useVoiceChannel";
import type { User } from "../types";
import { Icon } from "./Icon";

function initials(name: string): string {
  return name.split(/\s+/).map((part) => part[0]).join("").slice(0, 2).toUpperCase();
}

function hasVideo(stream: MediaStream | null): stream is MediaStream {
  return Boolean(stream?.getVideoTracks().some((track) =>
    track.readyState === "live" && !track.muted && track.enabled,
  ));
}

function MediaTile({
  stream,
  name,
  avatar,
  label,
  mirror = false,
  speaking = false,
  onPause,
  paused = false,
}: {
  stream: MediaStream | null;
  name: string;
  avatar?: string | null;
  label?: string;
  mirror?: boolean;
  speaking?: boolean;
  onPause?: () => void;
  paused?: boolean;
}) {
  const ref = useRef<HTMLVideoElement | null>(null);
  useEffect(() => {
    if (ref.current && stream && ref.current.srcObject !== stream) ref.current.srcObject = stream;
  }, [stream]);
  return (
    <article className={speaking ? "stage-person stage-person--speaking" : "stage-person"}>
      {hasVideo(stream) ? (
        <video ref={ref} autoPlay playsInline muted className={mirror ? "stage-person__video stage-person__video--mirror" : "stage-person__video"} />
      ) : avatar ? (
        <img className="stage-person__avatar" src={avatar} alt="" />
      ) : (
        <span className="stage-person__initials">{initials(name)}</span>
      )}
      <div className="stage-person__meta">
        <span>{name}</span>
        {label ? <small>{label}</small> : null}
      </div>
      {onPause && (hasVideo(stream) || paused) ? (
        <button type="button" className="stage-person__pause" onClick={onPause}>
          {paused ? "İzlemeyi aç" : "İzlemeyi kapat"}
        </button>
      ) : null}
    </article>
  );
}

export function VideoStage({
  currentUser,
  participants,
  voice,
  onLeave,
  onHide,
  qualityLabel,
}: {
  currentUser: User;
  participants: VoiceParticipant[];
  voice: VoiceChannelState;
  onLeave: () => void;
  onHide: () => void;
  qualityLabel: string;
}) {
  const stageRef = useRef<HTMLDivElement | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const remotes = useMemo(() => [...voice.remoteStreams.values()], [voice.remoteStreams]);
  const streamFor = (userId: number, kind: "camera" | "screen") =>
    remotes.find((item: RemoteVideoStream) => item.userId === userId && item.kind === kind)?.stream ?? null;

  const tiles = [
    {
      key: "self",
      name: `${currentUser.display_name || currentUser.username} (sen)`,
      avatar: currentUser.avatar_url,
      stream: voice.localCameraStream,
      mirror: true,
      speaking: false,
    },
    ...participants.map((participant) => ({
      key: `user-${participant.user_id}`,
      name: participant.username,
      avatar: participant.avatar_url,
      stream: voice.ignoredRemoteVideoIds.has(participant.user_id)
        ? null
        : streamFor(participant.user_id, "camera"),
      mirror: false,
      speaking: participant.speaking,
      userId: participant.user_id,
      paused: voice.ignoredRemoteVideoIds.has(participant.user_id),
    })),
    ...(voice.localScreenStream ? [{
      key: "self-screen",
      name: `${currentUser.display_name || currentUser.username} ekranı`,
      avatar: null,
      stream: voice.localScreenStream,
      mirror: false,
      speaking: false,
      label: "EKRAN",
    }] : []),
    ...remotes.filter((item) =>
      item.kind === "screen" &&
      hasVideo(item.stream) &&
      !voice.ignoredRemoteVideoIds.has(item.userId),
    ).map((item) => ({
      key: `screen-${item.userId}`,
      name: `${participants.find((p) => p.user_id === item.userId)?.username ?? "Katılımcı"} ekranı`,
      avatar: null,
      stream: item.stream,
      mirror: false,
      speaking: false,
      label: "EKRAN",
      userId: item.userId,
    })),
  ];

  useEffect(() => {
    const handler = () => setIsFullscreen(document.fullscreenElement === stageRef.current);
    document.addEventListener("fullscreenchange", handler);
    return () => document.removeEventListener("fullscreenchange", handler);
  }, []);

  async function toggleFullscreen() {
    if (!stageRef.current) return;
    if (document.fullscreenElement) await document.exitFullscreen();
    else await stageRef.current.requestFullscreen();
  }

  return (
    <section className="video-stage" ref={stageRef}>
      <header className="video-stage__header">
        <div><span className="video-stage__eyebrow">SESLİ SAHNE</span><strong>{tiles.length} katılımcı/yayın</strong></div>
        <span className="video-stage__quality"><span className="video-stage__live-dot" />{qualityLabel}</span>
      </header>
      <div className={`voice-grid voice-grid--${Math.min(tiles.length, 9)}`}>
        {tiles.map(({ key, ...tile }) => (
          <MediaTile
            key={key}
            {...tile}
            onPause={"userId" in tile && tile.userId ? () => voice.toggleRemoteVideo(tile.userId!) : undefined}
          />
        ))}
      </div>
      <div className="video-stage__controls" aria-label="Görüşme kontrolleri">
        <button className={voice.muted ? "stage-control stage-control--danger" : "stage-control"} onClick={voice.toggleMute}><Icon name={voice.muted ? "micOff" : "mic"} /><span>{voice.muted ? "Sesi aç" : "Sustur"}</span></button>
        <button className={voice.deafened ? "stage-control stage-control--danger" : "stage-control"} onClick={voice.toggleDeafen}><Icon name={voice.deafened ? "headphonesOff" : "headphones"} /><span>{voice.deafened ? "Dinle" : "Sağırlaştır"}</span></button>
        <button className={voice.cameraEnabled ? "stage-control stage-control--active" : "stage-control"} onClick={voice.toggleCamera}><Icon name="camera" /><span>Kamera</span></button>
        <button className={voice.screenShareEnabled ? "stage-control stage-control--active" : "stage-control"} onClick={voice.toggleScreenShare}><Icon name="screen" /><span>Paylaş</span></button>
        <button className="stage-control" onClick={onHide}><Icon name="hash" /><span>Sahneyi gizle</span></button>
        <button className="stage-control" onClick={() => void toggleFullscreen()}><Icon name="screen" /><span>{isFullscreen ? "Küçült" : "Tam ekran"}</span></button>
        <button className="stage-control stage-control--leave" onClick={onLeave}><Icon name="phone" /><span>Ayrıl</span></button>
      </div>
    </section>
  );
}
