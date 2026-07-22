import { useState } from "react";
import type { FormEvent } from "react";

import type { Server } from "../types";

interface ServerRailProps {
  servers: Server[];
  activeServerId: number | null;
  onSelect: (serverId: number) => void;
  onCreateServer: (name: string) => Promise<void>;
}

export function ServerRail({ servers, activeServerId, onSelect, onCreateServer }: ServerRailProps) {
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
    </nav>
  );
}
