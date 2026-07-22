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

export interface Server {
  id: number;
  name: string;
  description: string | null;
  icon_url: string | null;
  owner_id: number;
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
}

export interface Bot {
  id: number;
  name: string;
  command_prefix: string;
  matrix_user_id: string | null;
  is_active: boolean;
  created_at: string;
}

export interface PluginManifest {
  name: string;
  version: string;
  description: string | null;
  permissions: string[];
  commands: string[];
  installed: boolean;
  enabled: boolean;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
}
