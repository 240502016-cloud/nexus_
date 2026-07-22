import { useState } from "react";
import type { FormEvent } from "react";

interface LoginFormProps {
  onLogin: (username: string, password: string) => Promise<void>;
  onSwitchToRegister: () => void;
  error: string | null;
}

export function LoginForm({ onLogin, onSwitchToRegister, error }: LoginFormProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    try {
      await onLogin(username, password);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="login-screen">
      <form className="login-form" onSubmit={handleSubmit}>
        <h1>Nexus</h1>
        <label>
          Kullanıcı adı
          <input value={username} onChange={(event) => setUsername(event.target.value)} autoFocus />
        </label>
        <label>
          Parola
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        {error ? <p className="login-form__error">{error}</p> : null}
        <button type="submit" disabled={submitting || !username || !password}>
          {submitting ? "Giriş yapılıyor..." : "Giriş yap"}
        </button>
        <button type="button" className="login-form__link" onClick={onSwitchToRegister}>
          Hesabın yok mu? Kayıt ol
        </button>
      </form>
    </div>
  );
}
