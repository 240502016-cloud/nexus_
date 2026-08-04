// Highlight Generator domain contracts. Documentation artifact; backend mirrors them with Pydantic.

export type RecordingSourceType =
  | "MANUAL_UPLOAD"
  | "OBS_REPLAY_BUFFER"
  | "DISCORD_SCREEN_RECORDING"
  | "AUDIO_ONLY"
  | "FUTURE_CONNECTOR";

export type MarkerSourceType =
  | "MANUAL"
  | "COMMENTATOR"
  | "TRANSCRIPT"
  | "GAME_TELEMETRY"
  | "DISCORD_COMMAND";

export type HighlightCategory =
  | "SKILL"
  | "COMEDY"
  | "FAILURE"
  | "CHAOS"
  | "LORE_WORTHY";

export interface HighlightEventMarkerV1 {
  schemaVersion: "1.0";
  markerId: string;
  recordingId: string;
  source: MarkerSourceType;
  /** Preferred time axis after the file is known. */
  offsetMs?: number;
  /** Used to correlate a live marker to a later OBS upload. */
  occurredAt?: string;
  categoryHint?: HighlightCategory;
  participantPlayerIds: string[];
  summary?: string;
  manualPriority: 0 | 1;
  commentatorPriority?: number;
  gameEventSeverity?: number;
}

export interface HighlightSignals {
  manualMarker: number;
  commentatorPriority: number;
  gameEventSeverity: number;
  reactionIntensity: number;
  multiplePlayersReacting: number;
  laughterConfidence: number;
  voiceVolumeSpike: number;
  repeatedPhrase: number;
  suddenSilence: number;
  loreSimilarity: number;
  uniqueness: number;
  durationSuitability: number;
  confidencePenalty: number;
  duplicatePenalty: number;
  privacyPenalty: number;
}

export interface HighlightCandidate {
  id: string;
  recordingId: string;
  markerId?: string;
  startMs: number;
  endMs: number;
  anchorMs: number;
  score: number;
  primaryCategory: HighlightCategory;
  title: string;
  description: string;
  participantPlayerIds: string[];
  loreCandidate: boolean;
  memeCandidate: boolean;
  signals: HighlightSignals;
}

export interface TranscriptSegment {
  id: string;
  startMs: number;
  endMs: number;
  text: string;
  speakerLabel: string;
  /** Null unless a separate track or a player has confirmed the mapping. */
  playerId: string | null;
  confidence: number;
  reactionFlags: Array<"LAUGHTER" | "SHOUT" | "REPEATED_PHRASE" | "SUDDEN_SILENCE">;
}

export interface RenderVariant {
  layout: "LANDSCAPE" | "VERTICAL";
  introTitle: boolean;
  burnSubtitles: boolean;
  /** Optional verified transcript reaction; maximum 120 chars and rendered through safe ASS. */
  reactionText?: string;
  normalizeAudio: boolean;
  maximumDurationMs: number;
}
