import { useEffect, useState } from "react";

import type { VoiceChannelState } from "../hooks/useVoiceChannel";
import {
  deleteSoundboardClip,
  listSoundboardClips,
  saveSoundboardClip,
} from "../soundboardStorage";
import type { StoredSoundboardClip } from "../soundboardStorage";
import { Icon } from "./Icon";

const MAX_SOUND_BYTES = 2 * 1024 * 1024;
const ALLOWED_AUDIO_TYPES = new Set([
  "audio/mpeg",
  "audio/ogg",
  "audio/wav",
  "audio/x-wav",
  "audio/webm",
  "audio/mp4",
]);

const PRESETS = [
  { id: "airhorn" as const, name: "Airhorn", category: "Komik", symbol: "📣" },
  { id: "clap" as const, name: "Alkış", category: "Komik", symbol: "👏" },
  { id: "victory" as const, name: "Zafer", category: "Oyun", symbol: "🏆" },
  { id: "fail" as const, name: "Kaybettin", category: "Oyun", symbol: "💀" },
];

function readAudioDuration(file: File): Promise<number> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const audio = document.createElement("audio");
    let finished = false;
    const finish = (duration?: number, error?: Error) => {
      if (finished) return;
      finished = true;
      window.clearTimeout(timer);
      audio.removeAttribute("src");
      URL.revokeObjectURL(url);
      if (error) reject(error);
      else resolve(duration ?? 0);
    };
    const timer = window.setTimeout(
      () => finish(undefined, new Error("Ses dosyası doğrulanamadı.")),
      6_000,
    );
    audio.preload = "metadata";
    audio.onloadedmetadata = () => {
      const duration = audio.duration;
      if (!Number.isFinite(duration) || duration <= 0) {
        finish(undefined, new Error("Geçerli bir ses dosyası seçin."));
      } else {
        finish(duration);
      }
    };
    audio.onerror = () => finish(undefined, new Error("Ses biçimi tarayıcı tarafından açılamadı."));
    audio.src = url;
  });
}

export function SoundboardPanel({
  voice,
  currentUserId,
  onClose,
}: {
  voice: VoiceChannelState;
  currentUserId: number;
  onClose: () => void;
}) {
  const [clips, setClips] = useState<StoredSoundboardClip[]>([]);
  const [category, setCategory] = useState("Özel");
  const [activeCategory, setActiveCategory] = useState("Komik");
  const [error, setError] = useState<string | null>(null);
  const [playing, setPlaying] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    listSoundboardClips(currentUserId)
      .then((items) => {
        if (!cancelled) setClips(items);
      })
      .catch(() => {
        if (!cancelled) setError("Tarayıcı özel ses deposunu açamadı.");
      });
    return () => {
      cancelled = true;
    };
  }, [currentUserId]);

  async function play(id: string, action: () => Promise<void>) {
    setError(null);
    setPlaying(id);
    try {
      await action();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Ses çalınamadı");
    } finally {
      window.setTimeout(() => setPlaying((current) => current === id ? null : current), 450);
    }
  }

  async function addClip(file: File | undefined) {
    if (!file) return;
    setError(null);
    if (file.size > MAX_SOUND_BYTES) {
      setError("Özel soundboard sesi en fazla 2 MB olabilir.");
      return;
    }
    if (!ALLOWED_AUDIO_TYPES.has(file.type)) {
      setError("Yalnız MP3, OGG, WAV, WebM veya M4A ses dosyası eklenebilir.");
      return;
    }
    try {
      setUploading(true);
      const duration = await readAudioDuration(file);
      if (duration > 12) {
        setError("Özel soundboard sesi en fazla 12 saniye olabilir.");
        return;
      }
      const clip = await saveSoundboardClip(currentUserId, file, category);
      setClips((current) => [clip, ...current]);
      setActiveCategory(clip.category);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Ses eklenemedi");
    } finally {
      setUploading(false);
    }
  }

  async function removeClip(clip: StoredSoundboardClip) {
    await deleteSoundboardClip(clip.id);
    setClips((current) => current.filter((item) => item.id !== clip.id));
  }

  const categories = [
    ...new Set([...PRESETS.map((preset) => preset.category), ...clips.map((clip) => clip.category)]),
  ];
  const selectedCategory = categories.includes(activeCategory) ? activeCategory : categories[0];
  const visiblePresets = PRESETS.filter((preset) => preset.category === selectedCategory);
  const visibleClips = clips.filter((clip) => clip.category === selectedCategory);

  return (
    <section className="soundboard-panel" aria-label="Soundboard">
      <header className="soundboard-panel__header">
        <span className="soundboard-panel__mark">
          <Icon name="volume" />
        </span>
        <div className="soundboard-panel__heading">
          <strong>Soundboard</strong>
          <span>Sesler mevcut görüşme hattına güvenle karıştırılır</span>
        </div>
        <span className={voice.soundboardMuted ? "soundboard-panel__status muted" : "soundboard-panel__status"}>
          {voice.soundboardMuted ? "Kapalı" : `%${voice.soundboardVolume}`}
        </span>
        <button className="soundboard-panel__close" type="button" onClick={onClose} aria-label="Soundboard'u kapat">
          <Icon name="close" />
        </button>
      </header>

      <div className="soundboard-panel__level">
        <button
          type="button"
          className={voice.soundboardMuted ? "soundboard-panel__mute active" : "soundboard-panel__mute"}
          onClick={voice.toggleSoundboardMute}
          aria-pressed={voice.soundboardMuted}
        >
          <Icon name="volume" />
          <span>
            <strong>{voice.soundboardMuted ? "Sesi aç" : "Soundboard açık"}</strong>
            <small>{voice.soundboardMuted ? "Klipler karşıya gitmez" : "Klip çıkışı etkin"}</small>
          </span>
        </button>
        <label>
          <span>Çıkış seviyesi <strong>%{voice.soundboardVolume}</strong></span>
          <input
            type="range"
            min={0}
            max={200}
            step={5}
            value={voice.soundboardVolume}
            onChange={(event) => voice.setSoundboardVolume(Number(event.target.value))}
          />
        </label>
      </div>

      <nav className="soundboard-panel__tabs" aria-label="Soundboard kategorileri">
        {categories.map((group) => (
          <button
            type="button"
            key={group}
            className={selectedCategory === group ? "active" : ""}
            onClick={() => setActiveCategory(group)}
          >
            {group}
            <span>
              {PRESETS.filter((preset) => preset.category === group).length
                + clips.filter((clip) => clip.category === group).length}
            </span>
          </button>
        ))}
      </nav>

      <div className="soundboard-panel__library">
        <div className="soundboard-panel__library-heading">
          <div>
            <strong>{selectedCategory}</strong>
            <span>{visiblePresets.length + visibleClips.length} ses</span>
          </div>
          {playing ? <small><span /> Çalıyor</small> : null}
        </div>
        <div className="soundboard-panel__grid">
          {visiblePresets.map((preset) => (
            <button
              type="button"
              key={preset.id}
              className={playing === preset.id ? "soundboard-clip playing" : "soundboard-clip"}
              onClick={() => void play(preset.id, () => voice.playSoundboardPreset(preset.id))}
              disabled={voice.soundboardMuted}
            >
              <span className="soundboard-clip__symbol">{preset.symbol}</span>
              <span className="soundboard-clip__copy">
                <strong>{preset.name}</strong>
                <small>Hazır ses</small>
              </span>
              <Icon name="volume" />
            </button>
          ))}
          {visibleClips.map((clip) => (
            <span className="soundboard-panel__custom" key={clip.id}>
              <button
                type="button"
                className={playing === clip.id ? "soundboard-clip playing" : "soundboard-clip"}
                onClick={() => void play(clip.id, () => voice.playSoundboardClip(clip.blob))}
                disabled={voice.soundboardMuted}
              >
                <span className="soundboard-clip__symbol">♪</span>
                <span className="soundboard-clip__copy">
                  <strong>{clip.name}</strong>
                  <small>Özel ses</small>
                </span>
                <Icon name="volume" />
              </button>
              <button type="button" onClick={() => void removeClip(clip)} title="Özel sesi sil" aria-label={`${clip.name} sesini sil`}>
                <Icon name="trash" />
              </button>
            </span>
          ))}
          {visiblePresets.length + visibleClips.length === 0 ? (
            <p className="soundboard-panel__empty">Bu kategoride henüz bir ses yok.</p>
          ) : null}
        </div>
      </div>

      <div className="soundboard-panel__upload">
        <div>
          <strong>Özel ses ekle</strong>
          <span>MP3, OGG, WAV, WebM veya M4A · en fazla 2 MB / 12 sn</span>
        </div>
        <div className="soundboard-panel__upload-controls">
          <input
            value={category}
            onChange={(event) => setCategory(event.target.value)}
            maxLength={32}
            placeholder="Kategori"
            aria-label="Özel ses kategorisi"
          />
          <label className={uploading ? "disabled" : ""}>
            <Icon name="paperclip" />
            {uploading ? "Ekleniyor…" : "Dosya seç"}
            <input
              className="visually-hidden"
              type="file"
              disabled={uploading}
              accept="audio/mpeg,audio/ogg,audio/wav,audio/webm,audio/mp4"
              onChange={(event) => {
                void addClip(event.target.files?.[0]);
                event.target.value = "";
              }}
            />
          </label>
        </div>
      </div>
      {error ? <p className="soundboard-panel__error" role="alert">{error}</p> : null}
      <footer>
        Özel klipler yalnızca bu tarayıcıda saklanır ve sunucuya yüklenmez.
      </footer>
    </section>
  );
}
