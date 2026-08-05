import type { SVGProps } from "react";

export type IconName =
  | "settings" | "user" | "logout" | "mic" | "micOff" | "headphones" | "headphonesOff"
  | "camera" | "screen" | "phone" | "users" | "edit" | "trash" | "paperclip"
  | "send" | "file" | "close" | "bot" | "hash" | "volume" | "chevron" | "inbox"
  | "reply" | "search" | "pin" | "smile" | "gamepad" | "sliders" | "sparkles"
  | "external";

const paths: Record<IconName, React.ReactNode> = {
  settings: <><path d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.83 2.83-.06-.06A1.7 1.7 0 0 0 15 19.4a1.7 1.7 0 0 0-1 .6 1.7 1.7 0 0 0-.4 1.1V21h-4v-.09A1.7 1.7 0 0 0 8.6 19.4a1.7 1.7 0 0 0-1.88.34l-.06.06-2.83-2.83.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-.6-1 1.7 1.7 0 0 0-1.1-.4H3v-4h.09A1.7 1.7 0 0 0 4.6 8.6a1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.83-2.83.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-.6 1.7 1.7 0 0 0 .4-1.1V3h4v.09A1.7 1.7 0 0 0 15.4 4.6a1.7 1.7 0 0 0 1.88-.34l.06-.06 2.83 2.83-.06.06A1.7 1.7 0 0 0 19.4 9c.08.37.29.72.6 1 .3.27.68.4 1.1.4h.09v4h-.09c-.42 0-.8.13-1.1.4-.31.28-.52.63-.6 1Z"/></>,
  user: <><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></>,
  logout: <><path d="M10 17l5-5-5-5M15 12H3"/><path d="M14 3h5a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-5"/></>,
  mic: <><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3M8 21h8"/></>,
  micOff: <><path d="m3 3 18 18M9 9v2a3 3 0 0 0 5.1 2.1M15 9V6a3 3 0 0 0-5.8-1M5 11a7 7 0 0 0 11 5.7M19 11a7 7 0 0 1-.4 2.3M12 18v3M8 21h8"/></>,
  headphones: <><path d="M4 14v-2a8 8 0 0 1 16 0v2"/><path d="M4 14h3v7H5a2 2 0 0 1-2-2v-3a2 2 0 0 1 1-2ZM20 14h-3v7h2a2 2 0 0 0 2-2v-3a2 2 0 0 0-1-2Z"/></>,
  headphonesOff: <><path d="m3 3 18 18M4 14v-2a8 8 0 0 1 1.7-4.9M9.3 4.5A8 8 0 0 1 20 12v2M4 14h3v7H5a2 2 0 0 1-2-2v-3a2 2 0 0 1 1-2ZM20 14h-3v3"/></>,
  camera: <><path d="M14 8l2-2h5v12h-5l-2-2"/><rect x="3" y="6" width="13" height="12" rx="2"/></>,
  screen: <><rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8M12 17v4"/></>,
  phone: <path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.13 1 .37 2 .7 2.9a2 2 0 0 1-.45 2.1L8.1 10a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.45c.95.34 1.92.57 2.9.7a2 2 0 0 1 1.6 2Z"/>,
  users: <><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8"/></>,
  edit: <><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4Z"/></>,
  trash: <><path d="M3 6h18M8 6V4h8v2M19 6l-1 15H6L5 6M10 11v6M14 11v6"/></>,
  paperclip: <path d="m21.4 11.6-8.5 8.5a6 6 0 0 1-8.5-8.5l9-9a4 4 0 0 1 5.7 5.7l-9 9a2 2 0 0 1-2.9-2.8l8.4-8.5"/>,
  send: <><path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/></>,
  file: <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><path d="M14 2v6h6"/></>,
  close: <path d="M18 6 6 18M6 6l12 12"/>,
  bot: <><rect x="4" y="7" width="16" height="13" rx="3"/><path d="M12 3v4M8 12h.01M16 12h.01M8 16h8"/></>,
  hash: <path d="M4 9h16M3 15h16M10 3 8 21M16 3l-2 18"/>,
  volume: <><path d="M11 5 6 9H2v6h4l5 4ZM15.5 8.5a5 5 0 0 1 0 7M19 5a10 10 0 0 1 0 14"/></>,
  chevron: <path d="m6 9 6 6 6-6"/>,
  inbox: <><path d="M4 4h16v16H4Z"/><path d="M4 14h4l2 3h4l2-3h4"/></>,
  reply: <><path d="m9 17-5-5 5-5"/><path d="M4 12h9a7 7 0 0 1 7 7v1"/></>,
  search: <><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></>,
  pin: <><path d="m12 17v5M7 3h10M8 3l1 8-3 3h12l-3-3 1-8"/></>,
  smile: <><circle cx="12" cy="12" r="9"/><path d="M8 14s1.5 2 4 2 4-2 4-2M9 9h.01M15 9h.01"/></>,
  gamepad: <><path d="M8 6h8a6 6 0 0 1 5.7 7.9l-1.1 3.3a2.4 2.4 0 0 1-4 1l-1.8-2.2H9.2l-1.8 2.2a2.4 2.4 0 0 1-4-1l-1.1-3.3A6 6 0 0 1 8 6Z"/><path d="M7 10v4M5 12h4M16 11h.01M19 13h.01"/></>,
  sliders: <><path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h10M18 18h2"/><circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="16" cy="18" r="2"/></>,
  sparkles: <><path d="M12 3l1.9 4.6L18.5 9.5 13.9 11.4 12 16l-1.9-4.6L5.5 9.5l4.6-1.9Z"/><path d="M19 15l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8ZM5 2l.6 1.5L7 4.1l-1.4.6L5 6.2l-.6-1.5L3 4.1l1.4-.6Z"/></>,
  external: <><path d="M14 4h6v6"/><path d="m20 4-9 9"/><path d="M18 14v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4"/></>,
};

export function Icon({ name, ...props }: { name: IconName } & SVGProps<SVGSVGElement>) {
  return <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>{paths[name]}</svg>;
}
