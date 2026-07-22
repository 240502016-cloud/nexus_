import { useState } from "react";
import type { FormEvent } from "react";

interface RegisterFormProps {
  onRegister: (username: string, email: string, password: string) => Promise<void>;
  onSwitchToLogin: () => void;
  error: string | null;
}

export function RegisterForm({ onRegister, onSwitchToLogin, error }: RegisterFormProps) {
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    try {
      await onRegister(username, email, password);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="login-screen">
      <form className="login-form" onSubmit={handleSubmit}>
        <h1>Nexus</h1>
        <p className="login-form__subtitle">Yeni hesap oluştur</p>
        <label>
          Kullanıcı adı
          <input value={username} onChange={(event) => setUsername(event.target.value)} autoFocus />
        </label>
        <label>
          E-posta
          <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} />
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
        <button type="submit" disabled={submitting || !username || !email || !password}>
          {submitting ? "Hesap oluşturuluyor..." : "Kayıt ol"}
        </button>
        <button type="button" className="login-form__link" onClick={onSwitchToLogin}>
          Zaten hesabın var mı? Giriş yap
        </button>
      </form>
    </div>
  );
}
