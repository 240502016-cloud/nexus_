import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import { Icon } from "./Icon";

function extractCode(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) return "";
  try {
    const url = new URL(trimmed);
    return (url.searchParams.get("invite") ?? "").trim().toUpperCase();
  } catch {
    return trimmed.toUpperCase();
  }
}

export function JoinServerPanel({
  initialCode,
  onJoin,
  onClose,
}: {
  initialCode: string;
  onJoin: (code: string) => Promise<void>;
  onClose: () => void;
}) {
  const [value, setValue] = useState(initialCode);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => setValue(initialCode), [initialCode]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const code = extractCode(value);
    if (!code) return;
    setBusy(true);
    setError(null);
    try {
      await onJoin(code);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sunucuya katılınamadı");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="settings-overlay" onClick={onClose}>
      <form className="join-server-panel" onSubmit={submit} onClick={(event) => event.stopPropagation()}>
        <header>
          <div>
            <span className="panel-eyebrow">PAYLAŞILABİLİR DAVET</span>
            <h2>Sunucuya katıl</h2>
          </div>
          <button type="button" onClick={onClose} aria-label="Kapat"><Icon name="close" /></button>
        </header>
        <p>Arkadaşlık isteğine gerek yok. Sunucu sahibinin gönderdiği kodu veya bağlantıyı yapıştırın.</p>
        <input
          value={value}
          onChange={(event) => setValue(event.target.value)}
          placeholder="Örn. AB3D-EFGH veya davet bağlantısı"
          autoFocus
          autoComplete="off"
          spellCheck={false}
        />
        {error ? <div className="profile-panel__alert profile-panel__alert--error">{error}</div> : null}
        <button className="settings-panel__save" disabled={busy || !value.trim()}>
          {busy ? "Katılınıyor…" : "Sunucuya katıl"}
        </button>
      </form>
    </div>
  );
}
