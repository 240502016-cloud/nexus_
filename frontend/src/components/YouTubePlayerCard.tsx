export interface YouTubeMessageEvent {
  type: "youtube_state";
  video_id: string;
  playing: boolean;
  stopped: boolean;
  position_seconds: number;
  issued_at_ms: number;
}

function playbackPosition(event: YouTubeMessageEvent): number {
  const elapsed = event.playing
    ? Math.max(0, Date.now() - event.issued_at_ms) / 1000
    : 0;
  return Math.max(0, Math.floor(event.position_seconds + elapsed));
}

export function YouTubePlayerCard({
  event,
  body,
  active,
}: {
  event: YouTubeMessageEvent;
  body: string;
  active: boolean;
}) {
  const watchUrl = `https://www.youtube.com/watch?v=${event.video_id}`;
  if (!active) {
    return (
      <div className="youtube-card youtube-card--history">
        <strong>YouTube izleme odası güncellendi</strong>
        <span>{body}</span>
      </div>
    );
  }
  if (event.stopped) {
    return (
      <div className="youtube-card youtube-card--stopped">
        <div className="youtube-card__heading">
          <span className="youtube-card__mark">▶</span>
          <div><strong>YouTube izleme odası</strong><span>{body}</span></div>
        </div>
        <a href={watchUrl} target="_blank" rel="noreferrer">Videoyu YouTube’da aç</a>
      </div>
    );
  }

  const params = new URLSearchParams({
    autoplay: event.playing ? "1" : "0",
    enablejsapi: "1",
    playsinline: "1",
    rel: "0",
    start: String(playbackPosition(event)),
  });
  if (window.location.origin.startsWith("http")) params.set("origin", window.location.origin);

  return (
    <div className="youtube-card">
      <div className="youtube-card__heading">
        <span className="youtube-card__mark">▶</span>
        <div>
          <strong>YouTube izleme odası</strong>
          <span>{body}</span>
        </div>
        <span className={event.playing ? "youtube-card__state is-playing" : "youtube-card__state"}>
          {event.playing ? "Oynatılıyor" : "Duraklatıldı"}
        </span>
      </div>
      <div className="youtube-card__player">
        <iframe
          key={`${event.video_id}:${event.issued_at_ms}:${event.playing}`}
          src={`https://www.youtube.com/embed/${event.video_id}?${params.toString()}`}
          title="Nexus YouTube izleme odası"
          allow="autoplay; encrypted-media; picture-in-picture"
          allowFullScreen
          referrerPolicy="strict-origin-when-cross-origin"
        />
      </div>
      <div className="youtube-card__footer">
        <span>
          Ses gelmezse oynatıcıya tıklayın. Video sahibi gömmeyi kapattıysa içerik yalnız
          YouTube’da açılabilir.
        </span>
        <a className="youtube-card__external" href={watchUrl} target="_blank" rel="noreferrer">
          YouTube’da aç
        </a>
      </div>
    </div>
  );
}
