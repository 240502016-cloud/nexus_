import { useState } from "react";
import type { FormEvent } from "react";

import type { Server } from "../types";
import { Icon } from "./Icon";

interface ServerRailProps {
  servers: Server[];
  activeServerId: number | null;
  onSelect: (serverId: number) => void;
  onCreateServer: (name: string) => Promise<void>;
  onOpenJoin: () => void;
  inviteCount: number;
  onOpenInvites: () => void;
}

export function ServerRail({
  servers,
  activeServerId,
  onSelect,
  onCreateServer,
  onOpenJoin,
  inviteCount,
  onOpenInvites,
}: ServerRailProps) {
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");

  async function handleCreate(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    await onCreateServer(name.trim());
    setName("");
    setCreating(false);
  }

  return (
    <nav className="server-rail">
      <button
        type="button"
        className="server-icon server-icon--inbox"
        onClick={onOpenInvites}
        title="Sunucu davetleri"
        aria-label={`Sunucu davetleri${inviteCount ? `, ${inviteCount} bekleyen` : ""}`}
      >
        <Icon name="inbox" />
        {inviteCount ? <span className="server-icon__badge">{inviteCount > 9 ? "9+" : inviteCount}</span> : null}
      </button>
      <div className="server-rail__separator" />
      {servers.map((server) => (
        <button
          key={server.id}
          className={server.id === activeServerId ? "server-icon active" : "server-icon"}
          onClick={() => onSelect(server.id)}
          title={server.name}
        >
          {server.name.slice(0, 2).toUpperCase()}
        </button>
      ))}

      {creating ? (
        <form className="server-rail__create-form" onSubmit={handleCreate}>
          <input
            className="server-rail__create-input"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Sunucu adı"
            autoFocus
            onBlur={() => !name && setCreating(false)}
          />
        </form>
      ) : (
        <button className="server-icon server-icon--add" onClick={() => setCreating(true)} title="Sunucu oluştur">
          +
        </button>
      )}
      <button
        type="button"
        className="server-icon server-icon--join"
        onClick={onOpenJoin}
        title="Davet koduyla sunucuya katıl"
        aria-label="Davet koduyla sunucuya katıl"
      >
        ↪
      </button>
    </nav>
  );
}
