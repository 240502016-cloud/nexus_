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

export interface LoreParticipantDecision {
  user_id: number;
  decision: "pending" | "approved" | "rejected";
  decided_at: string | null;
}

export interface LoreCandidate {
  id: string;
  server_id: number;
  submitted_by_id: number;
  title: string;
  summary: string;
  category: string;
  sensitivity: "low" | "medium" | "high";
  allowed_modules: string[];
  status: "pending" | "confirmed" | "rejected";
  participants: LoreParticipantDecision[];
  lore_id: string | null;
  created_at: string;
  reviewed_at: string | null;
}

export interface LoreEntry {
  id: string;
  server_id: number;
  title: string;
  summary: string;
  category: string;
  sensitivity: "low" | "medium" | "high";
  allowed_modules: string[];
  participant_ids: number[];
  status: string;
  version: number;
  created_at: string;
  updated_at: string;
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

export type RoastTopic =
  | "GAMING_MISTAKES"
  | "FAILED_STRATEGIES"
  | "MATCH_STATISTICS"
  | "FUNNY_HIGHLIGHTS"
  | "CONFIRMED_PARTY_LORE"
  | "NAVIGATION"
  | "TEAMWORK"
  | "INVENTORY"
  | "TIMING"
  | "REACTIONS";

export interface RoastProfile {
  server_id: number;
  user_id: number;
  roast_enabled: boolean;
  maximum_intensity: number;
  allowed_topics: RoastTopic[];
  allow_party_lore: boolean;
  allow_highlights: boolean;
  allow_recent_failures: boolean;
  blocked_terms: string[];
  consent_version: number;
  updated_at: string;
}

export interface RoastSession {
  id: string;
  server_id: number;
  player_ids: number[];
  consent: Record<number, "PENDING" | "READY" | "DECLINED" | "REVOKED">;
  requested_intensity: number;
  status: "CONSENT_PENDING" | "ACTIVE" | "CANCELLED" | "ENDED";
  current_round: number;
  revision: number;
}

export interface RoastRound {
  id: string;
  session_id: string;
  round_number: number;
  target_player_id: number;
  effective_intensity: number;
  status: "GENERATING" | "VOTING" | "COMPLETED" | "SKIPPED";
  candidate_id: string | null;
  roast_text: string | null;
  angle: string | null;
}

export interface BoardGameAction {
  id: string;
  kind: string;
  label: string;
  cost: string;
  token: string;
}

export interface BoardGamePlayer {
  /** AI'ın oturduğu koltukta null olur; koltuk sahibi gerçek bir kullanıcı değildir. */
  user_id: number | null;
  ai: boolean;
  display_name: string;
  seat: number;
  tile_id: string;
  energy: number;
  scrap: number;
  fame: number;
  shield: number;
  momentum: number;
  sigils: string[];
  contribution: number;
}

export interface BoardGameEvent {
  id: number;
  type: string;
  sequence: number;
  revision: number;
  occurred_at: string;
  payload: Record<string, unknown>;
}

export interface BoardGameView {
  session_id: string;
  server_id: number;
  status: "ACTIVE" | "COMPLETED";
  revision: number;
  rules_version: string;
  theme: string;
  round: number;
  maximum_rounds: number;
  active_user_id: number | null;
  active_seat: number | null;
  active_is_ai: boolean;
  seat_count: number;
  action_points: number;
  chaos: number;
  chaos_limit: number;
  portal_charge: number;
  deposited_sigils: string[];
  players: BoardGamePlayer[];
  tiles: Record<string, { label: string; type: string; region: string; adjacent: string[]; sigil?: string }>;
  legal_actions: BoardGameAction[];
  events: BoardGameEvent[];
  group_outcome: string | null;
  winner_user_id: number | null;
  end_reason: string | null;
  rng_commitment: string;
  rng_seed_reveal: string | null;
}

export interface HiddenRoleGameView {
  session_id: string;
  server_id: number;
  status: "ACTIVE" | "COMPLETED";
  revision: number;
  round: number;
  phase: "CLAIM" | "VOTE" | "FINAL_DEDUCTION" | "COMPLETED";
  stability: number;
  crisis: {
    key: string;
    title: string;
    brief: string;
    public_clue: string;
    options: Array<{ id: "A" | "B" | "C"; disposition: "SEAL" | "REVEAL" | "REDIRECT"; title: string }>;
  } | null;
  /** `key` katılımcı anahtarıdır: insan için kullanıcı kimliği, AI koltuğu için "ai:<koltuk>". */
  players: Array<{ user_id: number | null; ai: boolean; key: string; display_name: string; seat: number; reputation: number; insight: number }>;
  human_player_count: number;
  claims: Array<{ id: string | null; user_id: number | null; key: string; subject_option_id: string; proposition: string; flavor_text: string; verdict: string | null }>;
  submitted_vote_count: number;
  submitted_deduction_count: number;
  round_results: Array<Record<string, unknown>>;
  own_private: {
    office: "SENTINEL" | "ARCHIVIST" | "ENVOY";
    mandate: "SEAL" | "REVEAL" | "REDIRECT";
    objective: string;
    clue: string | null;
    own_vote: string | null;
    deduction_submitted: boolean;
  };
  legal_action: { kind: "CLAIM" | "VOTE" | "DEDUCTION"; token: string } | null;
  result: {
    group_outcome: string;
    winner_key: string;
    winner_user_id: number | null;
    scores: Array<{ key: string; user_id: number | null; ai: boolean; total: number; insight: number; mandate_points: number; objective_points: number; deduction_points: number; reputation: number }>;
    assignments: Record<string, { office: string; mandate: string; objective: string }>;
  } | null;
  recap: string | null;
  rng_commitment: string;
}

export interface StorySafetyProfile {
  server_id: number;
  user_id: number;
  horror_level: number;
  violence_level: number;
  romance: "OFF" | "SOFT" | "FADE_TO_BLACK";
  player_conflict: "COOPERATIVE" | "CONTROLLED";
  betrayal: "OFF" | "NPC_ONLY";
  personal_jokes: boolean;
  dark_humor: boolean;
  version: number;
  updated_at: string;
}

export interface SharedStoryView {
  session_id: string;
  server_id: number;
  status: "ACTIVE" | "COMPLETED";
  revision: number;
  title: string;
  primary_goal: string;
  theme: string;
  chapter: number;
  chapter_count: number;
  phase: "SPOTLIGHT" | "JOINT_VOTE" | "COMPLETED";
  active_user_id: number | null;
  active_seat: number | null;
  active_is_ai: boolean;
  seat_count: number;
  scene_number: number;
  threat: number;
  goal_progress: number;
  mystery_progress: number;
  bond: number;
  characters: Array<{ user_id: number | null; ai: boolean; seat: number; name: string; archetype: string; traits: string[]; location: string; inventory: string[]; actions_taken: number }>;
  safety_envelope: Record<string, string | number | boolean>;
  spotlight_choices: Array<{ id: "INVESTIGATE" | "PROTECT" | "PRESS_ON"; label: string; risk: string; effects: Record<string, number> }>;
  joint_choices: Array<{ id: "STABILIZE" | "REVEAL_PATH" | "PUSH_FORWARD"; label: string; effects: Record<string, number> }>;
  submitted_vote_count: number;
  own_vote: string | null;
  action_token: string | null;
  chapter_results: Array<Record<string, unknown>>;
  ending_vector: Record<string, string> | null;
  prose: Array<{ source_event_id: number; content_kind: string; text: string; lore_reference_ids: string[] }>;
  rng_commitment: string;
}

export interface EscapeRoomNode {
  id: string;
  title: string;
  kind: string;
  status: "LOCKED" | "AVAILABLE" | "SOLVED";
  dependencies: string[];
  answer_type: string;
  answer_format: string;
  owner_role: string;
  required: boolean;
  attempt_count: number;
  submitted_count: number;
  submit_token: string | null;
  hint_token: string | null;
}

export interface EscapeRoomView {
  session_id: string;
  server_id: number;
  status: "ACTIVE" | "COMPLETED";
  revision: number;
  /** nadir3-v1 üç konsollu set, nadir2-v1 AI'sız iki kişilik odanın iki konsollu seti. */
  rules_version: "nadir3-v1" | "nadir2-v1";
  seat_count: number;
  timer_mode: "RELAXED" | "STANDARD_45" | "CHALLENGE_30";
  elapsed_seconds: number;
  overtime: boolean;
  nodes: EscapeRoomNode[];
  players: Array<{ user_id: number | null; ai: boolean; display_name: string; seat: number; role: "ENGINEER" | "ANALYST" | "NAVIGATOR" }>;
  /** AI'ın tuttuğu konsolun açık düğümler için paylaştığı özel ipuçları. */
  ai_consoles: Array<{ role: "ENGINEER" | "ANALYST" | "NAVIGATOR"; clues: Record<string, string> }>;
  shared_inventory: string[];
  own_private: { role: "ENGINEER" | "ANALYST" | "NAVIGATOR"; clues: Record<string, string>; ability_available: boolean };
  hints: Array<{ node_id: string; tier: number; text: string }>;
  host_messages: Array<{ source_event_id: number; text: string; lore_reference_ids: string[] }>;
  result: { grade: string; elapsed_seconds: number; overtime: boolean; assisted: boolean; optional_solved: boolean; max_hint_tier: number } | null;
  rng_commitment: string;
}
