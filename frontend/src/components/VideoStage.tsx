import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";

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

type StageTileKind = "profile" | "camera" | "screen";

interface StageTile {
  key: string;
  kind: StageTileKind;
  name: string;
  avatar?: string | null;
  stream: MediaStream | null;
  mirror: boolean;
  speaking: boolean;
  label?: string;
  userId?: number;
  paused?: boolean;
}

function MediaTile({
  stream,
  kind,
  name,
  avatar,
  label,
  mirror = false,
  speaking = false,
  onPause,
  paused = false,
  focused = false,
  onFocus,
}: {
  stream: MediaStream | null;
  kind: StageTileKind;
  name: string;
  avatar?: string | null;
  label?: string;
  mirror?: boolean;
  speaking?: boolean;
  onPause?: () => void;
  paused?: boolean;
  focused?: boolean;
  onFocus?: () => void;
}) {
  const ref = useRef<HTMLVideoElement | null>(null);
  useEffect(() => {
    if (ref.current && stream && ref.current.srcObject !== stream) ref.current.srcObject = stream;
  }, [stream]);
  const className = [
    "stage-person",
    `stage-person--${kind}`,
    speaking ? "stage-person--speaking" : "",
    focused ? "stage-person--focused" : "",
  ].filter(Boolean).join(" ");
  return (
    <article
      className={className}
      onClick={onFocus}
      onKeyDown={(event) => {
        if (!onFocus || (event.key !== "Enter" && event.key !== " ")) return;
        event.preventDefault();
        onFocus();
      }}
      role={onFocus ? "button" : undefined}
      tabIndex={onFocus ? 0 : undefined}
      title={onFocus ? (focused ? "Odak görünümünden çık" : `${name} akışına odaklan`) : undefined}
      aria-label={onFocus ? (focused ? `${name} odak görünümünden çık` : `${name} akışına odaklan`) : undefined}
    >
      {hasVideo(stream) ? (
        <video
          ref={ref}
          autoPlay
          playsInline
          muted
          disablePictureInPicture
          className={mirror ? "stage-person__video stage-person__video--mirror" : "stage-person__video"}
        />
      ) : avatar ? (
        <img className="stage-person__avatar" src={avatar} alt="" />
      ) : (
        <span className="stage-person__initials">{initials(name)}</span>
      )}
      <div className="stage-person__meta">
        <span>{name}</span>
        {label ? <small>{label}</small> : null}
      </div>
      {onFocus ? (
        <span className="stage-person__focus-hint">{focused ? "Izgaraya dön" : "Odakla"}</span>
      ) : null}
      {onPause && (hasVideo(stream) || paused) ? (
        <button
          type="button"
          className="stage-person__pause"
          onClick={(event) => {
            event.stopPropagation();
            onPause();
          }}
        >
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
}: {
  currentUser: User;
  participants: VoiceParticipant[];
  voice: VoiceChannelState;
  onLeave: () => void;
  onHide: () => void;
}) {
  const stageRef = useRef<HTMLDivElement | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [focusedTileKey, setFocusedTileKey] = useState<string | null>(null);
  const remotes = useMemo(() => [...voice.remoteStreams.values()], [voice.remoteStreams]);
  const streamFor = (userId: number, kind: "camera" | "screen") =>
    remotes.find((item: RemoteVideoStream) => item.userId === userId && item.kind === kind)?.stream ?? null;

  const tiles: StageTile[] = [
    ...(!hasVideo(voice.localScreenStream) || hasVideo(voice.localCameraStream) ? [{
      key: "self",
      kind: hasVideo(voice.localCameraStream) ? "camera" as const : "profile" as const,
      name: `${currentUser.display_name || currentUser.username} (sen)`,
      avatar: currentUser.avatar_url,
      stream: voice.localCameraStream,
      mirror: true,
      speaking: false,
    }] : []),
    ...participants.filter((participant) => {
      if (voice.ignoredRemoteVideoIds.has(participant.user_id)) return true;
      const camera = streamFor(participant.user_id, "camera");
      const screen = streamFor(participant.user_id, "screen");
      // Kamera yokken ekran paylaşımı yapan kişinin profil kartını ayrıca göstermeye gerek yok.
      return !hasVideo(screen) || hasVideo(camera);
    }).map((participant) => ({
      key: `user-${participant.user_id}`,
      kind: hasVideo(streamFor(participant.user_id, "camera")) ? "camera" as const : "profile" as const,
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
      kind: "screen" as const,
      name: `${currentUser.display_name || currentUser.username} ekranı`,
      avatar: null,
      stream: voice.localScreenStream,
      mirror: false,
      speaking: false,
      label: voice.screenAudioEnabled ? "EKRAN + SES" : "EKRAN",
    }] : []),
    ...remotes.filter((item) =>
      item.kind === "screen" &&
      hasVideo(item.stream) &&
      !voice.ignoredRemoteVideoIds.has(item.userId),
    ).map((item) => ({
      key: `screen-${item.userId}`,
      kind: "screen" as const,
      name: `${participants.find((p) => p.user_id === item.userId)?.username ?? "Katılımcı"} ekranı`,
      avatar: null,
      stream: item.stream,
      mirror: false,
      speaking: false,
      label: "EKRAN",
      userId: item.userId,
    })),
  ];
  const focusedTile = focusedTileKey
    ? tiles.find((tile) => tile.key === focusedTileKey) ?? null
    : null;
  const broadcastTile = tiles.find((tile) => tile.kind === "screen" && hasVideo(tile.stream)) ?? null;
  const previewTiles = broadcastTile
    ? tiles.filter((tile) => tile.key !== broadcastTile.key)
    : [];

  useEffect(() => {
    if (focusedTileKey && !tiles.some((tile) => tile.key === focusedTileKey)) {
      setFocusedTileKey(null);
    }
  }, [focusedTileKey, tiles]);

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

  async function hideStage() {
    if (document.fullscreenElement === stageRef.current) {
      await document.exitFullscreen().catch(() => {});
    }
    onHide();
  }

  async function leaveStage() {
    if (document.fullscreenElement === stageRef.current) {
      await document.exitFullscreen().catch(() => {});
    }
    onLeave();
  }

  function renderTile(tile: StageTile, focused = false) {
    const { key, ...mediaTile } = tile;
    return (
      <MediaTile
        key={key}
        {...mediaTile}
        focused={focused}
        onFocus={() => setFocusedTileKey((current) => current === key ? null : key)}
        onPause={"userId" in mediaTile && mediaTile.userId
          ? () => voice.toggleRemoteVideo(mediaTile.userId!)
          : undefined}
      />
    );
  }

  const toolbarTarget = document.getElementById("channel-toolbar-portal");

  return (
    <section
      className={[
        "video-stage",
        broadcastTile ? "video-stage--broadcast" : "",
        focusedTile ? "video-stage--focused" : "",
      ].filter(Boolean).join(" ")}
      ref={stageRef}
    >
      {toolbarTarget
        ? createPortal(
            <button
              type="button"
              className="toolbar-action channel-tool--fullscreen"
              onClick={() => void toggleFullscreen()}
              title="Sahneyi tam ekran göster"
            >
              <Icon name="screen" />
              <span>Tam ekran</span>
            </button>,
            toolbarTarget,
          )
        : null}
      {isFullscreen ? (
        <div
          className="video-stage__overlay-controls video-stage__overlay-controls--full"
          aria-label="Sahne kontrolleri"
          onClick={(event) => event.stopPropagation()}
        >
          <div className="video-stage__control-group" aria-label="Ses ve medya kontrolleri">
            <button className={voice.muted ? "stage-control stage-control--danger" : "stage-control"} onClick={voice.toggleMute} title={voice.muted ? "Sesi aç" : "Sustur"}><Icon name={voice.muted ? "micOff" : "mic"} /><span>{voice.muted ? "Sesi aç" : "Sustur"}</span></button>
            <button className={voice.deafened ? "stage-control stage-control--danger" : "stage-control"} onClick={voice.toggleDeafen} title={voice.deafened ? "Dinle" : "Sağırlaştır"}><Icon name={voice.deafened ? "headphonesOff" : "headphones"} /><span>{voice.deafened ? "Dinle" : "Sağırlaştır"}</span></button>
            <button className={voice.cameraEnabled ? "stage-control stage-control--active" : "stage-control"} onClick={voice.toggleCamera} title="Kamera"><Icon name="camera" /><span>Kamera</span></button>
            <button className={voice.screenShareEnabled ? "stage-control stage-control--active" : "stage-control"} onClick={voice.toggleScreenShare} title="Ekran paylaş"><Icon name="screen" /><span>Paylaş</span></button>
          </div>
          <div className="video-stage__control-group" aria-label="Sahne görünümü">
            <button className="stage-control" onClick={() => void hideStage()} title="Sahneyi gizle"><Icon name="hash" /><span>Sahneyi gizle</span></button>
            <button className="stage-control" onClick={() => void toggleFullscreen()} title="Tam ekrandan çık"><Icon name="screen" /><span>Küçült</span></button>
          </div>
          <div className="video-stage__control-group video-stage__control-group--danger" aria-label="Görüşmeden ayrıl">
            <button className="stage-control stage-control--leave" onClick={() => void leaveStage()} title="Ses kanalından ayrıl"><Icon name="phone" /><span>Ayrıl</span></button>
          </div>
        </div>
      ) : null}
      {focusedTile ? (
        <div className="voice-focus-layout">
          {renderTile(focusedTile, true)}
        </div>
      ) : broadcastTile ? (
        <div className={previewTiles.length ? "broadcast-layout broadcast-layout--with-previews" : "broadcast-layout"}>
          <div className="broadcast-layout__main">
            {renderTile(broadcastTile)}
          </div>
          {previewTiles.length ? (
            <aside className="broadcast-layout__previews" aria-label="Diğer katılımcılar">
              {previewTiles.map((tile) => renderTile(tile))}
            </aside>
          ) : null}
        </div>
      ) : (
        <div className={`voice-grid voice-grid--${Math.min(tiles.length, 9)}`}>
          {tiles.map((tile) => renderTile(tile))}
        </div>
      )}
    </section>
  );
}
