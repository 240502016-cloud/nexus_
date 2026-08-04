import type {
  HighlightCandidate,
  HighlightCategory,
  HighlightEventMarkerV1,
  RecordingSourceType,
  RenderVariant,
} from "./media-contract";

export interface CreateRecordingRequest {
  serverId: number;
  sessionId?: string;
  sourceId?: string;
  sourceType: RecordingSourceType;
  originalFileName: string;
  byteSize: number;
  sha256: string;
  captureStartedAt?: string;
  captureEndedAt?: string;
  contentType: "video/mp4" | "video/x-matroska" | "audio/wav" | "audio/mpeg";
}

export interface RecordingUploadTarget {
  recordingId: string;
  status: "AWAITING_UPLOAD" | "ALREADY_EXISTS";
  contentUrl?: string;
  expiresAt?: string;
}

export interface CompleteRecordingUploadRequest {
  byteSize: number;
  sha256: string;
}

export interface Recording {
  id: string;
  serverId: number;
  sessionId?: string;
  sourceType: RecordingSourceType;
  status:
    | "AWAITING_UPLOAD"
    | "UPLOADED"
    | "PROBING"
    | "READY"
    | "INVALID"
    | "DELETION_QUEUED"
    | "DELETED";
  durationMs?: number;
  width?: number;
  height?: number;
  hasAudio?: boolean;
  createdAt: string;
}

export type CreateMarkerRequest = Omit<HighlightEventMarkerV1, "recordingId">;

export interface AnalyzeRecordingRequest {
  markerIds?: string[];
  includeTranscriptSignals: boolean;
  forceReanalyze?: boolean;
}

export interface ProcessingJobResponse {
  jobId: string;
  stage: string;
  status: "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED" | "CANCELLED";
  progress: number;
  errorCode?: string;
}

export interface CandidatePreviewResponse {
  candidate: HighlightCandidate;
  previewUrl?: string;
  transcriptExcerpt?: Array<{ startMs: number; endMs: number; text: string }>;
}

export interface RenderHighlightRequest {
  candidateId: string;
  startMs?: number;
  endMs?: number;
  titleOverride?: string;
  descriptionOverride?: string;
  variant: RenderVariant;
}

export interface RenderedHighlight {
  id: string;
  candidateId: string;
  category: HighlightCategory;
  variant: "LANDSCAPE" | "VERTICAL" | "COMPILATION";
  title: string;
  description: string;
  assetUrl: string;
  thumbnailUrl: string;
  durationMs: number;
  width: number;
  height: number;
  byteSize: number;
  createdAt: string;
}

export interface ChangeTrimRequest {
  startMs: number;
  endMs: number;
}

export interface GenerateVerticalRequest {
  cropCenterX?: number;
  cropCenterY?: number;
  burnSubtitles: boolean;
}

export interface HighlightFeedbackRequest {
  playerId: number;
  type: "GOOD" | "WRONG_MOMENT" | "TRIM_EARLIER" | "TRIM_LATER" | "TOO_LONG" | "SAVE";
  details?: string;
}

export interface GenerateCompilationRequest {
  sessionId: string;
  candidateIds: string[];
  maximumDurationMs: number;
  title?: string;
  burnSubtitles: boolean;
}

export interface CompilationResponse {
  jobId: string;
  status: "QUEUED" | "RUNNING" | "READY" | "FAILED";
  highlight?: RenderedHighlight;
}
