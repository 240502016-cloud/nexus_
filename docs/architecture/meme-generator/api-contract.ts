import type { MemeEventV1 } from "./event-contract";
import type { CaptionZoneId, MemeCategory, MemeTemplate } from "./template-contract";

export type MemeFeedbackType =
  | "FUNNY"
  | "FORCED"
  | "TOO_HARSH"
  | "REPETITIVE"
  | "WRONG_CONTEXT"
  | "SAVE";

export interface SubmitMemeJobRequest {
  event: MemeEventV1;
  preferredFormats?: Array<
    | "TEXT_CARD"
    | "CAPTIONED_TEMPLATE"
    | "SCREENSHOT"
    | "ACHIEVEMENT_CARD"
    | "PATCH_NOTES"
    | "NEWS_REPORT"
    | "PLAYER_STATS"
    | "EXPECTATION_REALITY"
    | "REACTION_CARD"
  >;
  desiredHarshness?: 0 | 1 | 2 | 3;
}

export interface MemeJobAccepted {
  jobId: string;
  eventId: string;
  status: "QUEUED";
}

export interface CaptionCandidate {
  id: string;
  rank: number;
  templateId: string;
  category: MemeCategory;
  captions: Partial<Record<CaptionZoneId, string>>;
  targetPlayerId: string | null;
  loreReferences: number[];
  harshness: 0 | 1 | 2 | 3;
  qualityScore: number;
  previewUrl?: string;
}

export interface MemeCandidatePreviewResponse {
  jobId: string;
  memeWorthy: boolean;
  memeWorthinessScore: number;
  reasoningCode: string;
  candidates: CaptionCandidate[];
}

export interface RenderMemeRequest {
  candidateId: string;
  templateId?: string;
  captionOverrides?: Partial<Record<CaptionZoneId, string>>;
  outputFormat?: "PNG" | "JPEG" | "WEBP";
}

export interface GeneratedMeme {
  id: string;
  jobId: string;
  template: Pick<MemeTemplate, "id" | "name" | "aspectRatio">;
  category: MemeCategory;
  targetPlayerId: string | null;
  assetUrl: string;
  width: number;
  height: number;
  mimeType: string;
  byteSize: number;
  createdAt: string;
}

export interface RegenerateCaptionRequest {
  keepTemplate: boolean;
  feedbackHint?: "SHORTER" | "GENTLER" | "MORE_SPECIFIC" | "NO_LORE";
}

export interface ChangeTemplateRequest {
  templateId: string;
  keepCaptions: boolean;
}

export interface SubmitMemeFeedbackRequest {
  playerId: number;
  type: MemeFeedbackType;
  details?: string;
}

export interface SessionMemePackResponse {
  sessionId: string;
  status: "EMPTY" | "READY" | "GENERATING";
  memes: GeneratedMeme[];
  nextCursor?: string;
}

export interface DeleteMemeResponse {
  id: string;
  state: "DELETION_QUEUED";
}
