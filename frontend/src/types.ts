// Backend'deki app/core/schemas.py ile bire bir uyumlu tutulmalıdır (alan adları dahil -
// backend JSON'ı snake_case döner, burada da kasıtlı olarak snake_case kullanılıyor).

export type ChannelType = "text" | "voice";

export interface User {
  id: number;
  username: string;
  email: string;
  display_name: string | null;
  avatar_url: string | null;
  matrix_user_id: string | null;
  is_active: boolean;
  created_at: string;
}

export interface PublicUser {
  id: number;
  username: string;
  display_name: string | null;
  avatar_url: string | null;
  created_at: string;
}

export interface Friend {
  friendship_id: number;
  user: PublicUser;
  since: string;
}

export interface FriendRequest {
  id: number;
  user: PublicUser;
  direction: "incoming" | "outgoing";
  created_at: string;
}

export interface FriendRequestList {
  incoming: FriendRequest[];
  outgoing: FriendRequest[];
}

export interface DirectConversation {
  id: number;
  friend: PublicUser;
  created_at: string;
}

export interface Server {
  id: number;
  name: string;
  description: string | null;
  icon_url: string | null;
  owner_id: number;
  created_at: string;
}

export interface ServerInvite {
  id: number;
  server_id: number;
  server_name: string;
  server_icon_url: string | null;
  inviter: PublicUser;
  invitee: PublicUser;
  direction: "incoming" | "outgoing";
  status: "pending" | "accepted" | "rejected" | "cancelled";
  created_at: string;
  updated_at: string;
}

export interface ServerInviteList {
  incoming: ServerInvite[];
  outgoing: ServerInvite[];
}

export interface ServerJoinCode {
  code: string;
  created_at: string;
}

export interface Channel {
  id: number;
  server_id: number;
  name: string;
  type: ChannelType;
  topic: string | null;
  position: number;
  matrix_room_id: string | null;
  created_at: string;
}

export interface Member {
  id: number;
  username: string;
  display_name: string | null;
  avatar_url: string | null;
  joined_at: string;
}

export interface Role {
  id: number;
  server_id: number;
  name: string;
  color: string | null;
  position: number;
  permissions: number;
  is_default: boolean;
  created_at: string;
}

export interface Message {
  event_id: string;
  sender: string;
  content: string;
  origin_server_ts: number | null;
  client_id?: string | null;
  hidden?: boolean;
  is_bot?: boolean;
  edited?: boolean;
  reply_to?: MessageReplyPreview | null;
  reactions?: MessageReaction[];
  mentioned_user_ids?: number[];
  // Yalnızca istemci tarafındaki iyimser mesajlarda kullanılır; API snapshot'larında bulunmaz.
  delivery_status?: "sending" | "failed";
}

export interface MessageReaction {
  emoji: string;
  count: number;
  me: boolean;
}

export interface MessageReplyPreview {
  event_id: string;
  sender: string;
  content: string;
}

export interface MessageReactionUpdate {
  event_id: string;
  reactions: MessageReaction[];
}

export interface PinnedMessages {
  items: Message[];
  can_manage: boolean;
}

export interface AiConversation {
  id: number;
  model: string;
  title: string | null;
  created_at: string;
}

export type AiJobStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";

export interface AiJob {
  id: number;
  conversation_id: number;
  user_message_id: number;
  assistant_message_id: number | null;
  status: AiJobStatus;
  attempts: number;
  output_text: string | null;
  cancel_requested: boolean;
  error: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface Attachment {
  id: string;
  name: string;
  url: string;
  size: number;
  content_type: string;
  is_image: boolean;
}

export interface MessagePage {
  items: Message[];
  next_cursor: string | null;
  has_more: boolean;
}

export interface Bot {
  id: number;
  name: string;
  command_prefix: string;
  matrix_user_id: string | null;
  is_active: boolean;
  created_at: string;
  plugin_names: string[];
}

export interface PluginManifest {
  name: string;
  version: string;
  description: string | null;
  permissions: string[];
  commands: string[];
  installed: boolean;
  enabled: boolean;
  requires_bot_link: boolean;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
}

export type CommentaryIntensity = "LOW" | "NORMAL" | "HIGH";
export type CommentarySessionTone = "CALM" | "FOCUSED" | "PLAYFUL" | "TENSE" | "UPSET" | "UNKNOWN";

export interface CommentatorProfile {
  key: string;
  name: string;
  description: string;
  max_chars: number;
  harshness: number;
  lore_probability: number;
  tones: string[];
}

export interface CommentarySession {
  id: string;
  server_id: number;
  game_key: string;
  player_ids: number[];
  profile_key: string;
  intensity: CommentaryIntensity;
  silent_mode: boolean;
  text_to_speech_enabled: boolean;
  current_tone: CommentarySessionTone;
  status: string;
  revision: number;
  output_channel_id: number | null;
  started_at: string;
  ended_at: string | null;
}

export interface CommentatorEvent {
  id: string;
  event_id: string;
  category: string;
  summary: string;
  occurred_at: string;
  trigger_score: number;
  trigger_decision: string;
  processing_state: string;
}

export interface GeneratedCommentary {
  id: string;
  session_id: string;
  source_event_ids: string[];
  should_comment: boolean;
  commentary: string | null;
  target_player_id: number | null;
  tone: string | null;
  lore_references: string[];
  confidence: number;
  reason_code: string;
  dispatch_state: string;
  created_at: string;
  delivered_at: string | null;
}

export interface CommentaryHistory {
  session: CommentarySession;
  events: CommentatorEvent[];
  commentary: GeneratedCommentary[];
}

export type MemeMomentType =
  | "FAILURE"
  | "SUCCESS"
  | "BETRAYAL"
  | "TEAM_EVENT"
  | "MILESTONE"
  | "PREPARATION"
  | "NAVIGATION"
  | "PANIC"
  | "SILENCE"
  | "MANUAL_NOTE";

export interface MemeJob {
  job_id: string;
  event_id: string;
  status: string;
  meme_worthy: boolean;
  meme_worthiness_score: number;
  reasoning_code: string;
}

export interface MemeCaptionCandidate {
  id: string;
  rank: number;
  template_key: string;
  template_version: number;
  template_name: string;
  category: string;
  captions: Record<string, string>;
  target_player_id: number | null;
  lore_references: string[];
  harshness: number;
  quality_score: number;
}

export interface MemeCandidateResponse {
  job_id: string;
  status: string;
  meme_worthy: boolean;
  meme_worthiness_score: number;
  reasoning_code: string;
  error_code: string | null;
  candidates: MemeCaptionCandidate[];
}

export interface GeneratedMeme {
  id: string;
  job_id: string;
  template_key: string;
  template_name: string;
  category: string;
  captions: Record<string, string>;
  target_player_id: number | null;
  asset_url: string;
  width: number;
  height: number;
  mime_type: string;
  byte_size: number;
  created_at: string;
}

export interface HighlightRecording {
  id: string;
  server_id: number;
  session_id: string | null;
  source_type: string;
  original_filename: string;
  status: string;
  upload_url: string | null;
  byte_size: number | null;
  duration_ms: number | null;
  width: number | null;
  height: number | null;
  has_audio: boolean | null;
  error_code: string | null;
  created_at: string;
}

export interface HighlightCandidate {
  id: string;
  recording_id: string;
  marker_id: string;
  start_ms: number;
  end_ms: number;
  anchor_ms: number;
  score: number;
  primary_category: string;
  title: string;
  description: string;
  participant_player_ids: number[];
  status: string;
}

export interface RenderedHighlight {
  id: string;
  candidate_id: string;
  status: string;
  category: string;
  variant: string;
  title: string;
  description: string;
  video_url: string | null;
  thumbnail_url: string | null;
  duration_ms: number;
  width: number | null;
  height: number | null;
  error_code: string | null;
  created_at: string;
}
