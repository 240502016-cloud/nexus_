import { useEffect, useRef } from "react";

import type { VoiceParticipant, VideoKind } from "../hooks/useVoiceChannel";
import type { User } from "../types";

interface VideoTileProps {
  stream: MediaStream;
  label: string;
  muted: boolean;
  mirror?: boolean;
  badge?: string;
}

function VideoTile({ stream, label, muted, mirror, badge }: VideoTileProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);

  useEffect(() => {
    const el = videoRef.current;
    if (el && el.srcObject !== stream) {
      el.srcObject = stream;
    }
  }, [stream]);

  return (
    <div className="video-tile">
      <video
        ref={videoRef}
        autoPlay
        playsInline
        muted={muted}
        className={mirror ? "video-tile__video video-tile__video--mirror" : "video-tile__video"}
      />
      <span className="video-tile__label">
        {badge ? <span className="video-tile__badge">{badge}</span> : null}
        {label}
      </span>
    </div>
  );
}

function hasVideo(stream: MediaStream): boolean {
  return stream.getVideoTracks().some((t) => t.readyState === "live");
}

interface VideoStageProps {
  currentUser: User;
  participants: VoiceParticipant[];
  localVideoStream: MediaStream | null;
  localVideoKind: VideoKind;
  remoteStreams: Map<number, MediaStream>;
}

export function VideoStage({
  currentUser,
  participants,
  localVideoStream,
  localVideoKind,
  remoteStreams,
}: VideoStageProps) {
  const remoteTiles = Array.from(remoteStreams.entries()).filter(([, stream]) => hasVideo(stream));

  const hasAnyVideo = (localVideoStream && hasVideo(localVideoStream)) || remoteTiles.length > 0;
  if (!hasAnyVideo) return null;

  const nameOf = (userId: number) =>
    participants.find((p) => p.user_id === userId)?.username ?? `#${userId}`;

  return (
    <div className="video-stage">
      <div className="video-stage__grid">
        {localVideoStream && hasVideo(localVideoStream) ? (
          <VideoTile
            stream={localVideoStream}
            label={`${currentUser.username} (sen)`}
            muted
            mirror={localVideoKind === "camera"}
            badge={localVideoKind === "screen" ? "🖥️" : "📷"}
          />
        ) : null}
        {remoteTiles.map(([userId, stream]) => (
          <VideoTile key={userId} stream={stream} label={nameOf(userId)} muted />
        ))}
      </div>
    </div>
  );
}
