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
      <div className="login-screen__glow login-screen__glow--one" />
      <div className="login-screen__glow login-screen__glow--two" />
      <section className="login-visual" aria-label="Nexus iletişim ağı">
        <div className="login-visual__brand">
          <span className="login-visual__mark">N</span>
          <span>NEXUS</span>
        </div>
        <div className="login-visual__art" aria-hidden="true">
          <span className="login-visual__orb login-visual__orb--core">N</span>
          <span className="login-visual__orb login-visual__orb--one" />
          <span className="login-visual__orb login-visual__orb--two" />
          <span className="login-visual__orb login-visual__orb--three" />
          <span className="login-visual__line login-visual__line--one" />
          <span className="login-visual__line login-visual__line--two" />
          <span className="login-visual__line login-visual__line--three" />
        </div>
        <div className="login-visual__copy">
          <span className="login-form__eyebrow">TEK MERKEZ. SINIRSIZ İLETİŞİM.</span>
          <h2>Ekibinle aynı frekansta kal.</h2>
          <p>Mesajlar, yüksek kaliteli görüşmeler ve canlı paylaşımlar tek, güvenli çalışma alanında.</p>
        </div>
      </section>
      <form className="login-form" onSubmit={handleSubmit}>
        <span className="login-form__eyebrow">TEKRAR HOŞ GELDİN</span>
        <h1>Hesabına giriş yap</h1>
        <p className="login-form__subtitle">Topluluğun seni bekliyor.</p>
        <label>
          Kullanıcı adı
          <input
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            autoComplete="username"
            placeholder="kullaniciadi"
            autoFocus
          />
        </label>
        <label>
          Parola
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
            placeholder="••••••••"
          />
        </label>
        {error ? <p className="login-form__error">{error}</p> : null}
        <button type="submit" disabled={submitting || !username || !password}>
          {submitting ? "Giriş yapılıyor..." : "Giriş yap"}
        </button>
        <button type="button" className="login-form__link" onClick={onSwitchToRegister}>
          Hesabın yok mu? Kayıt ol
        </button>
        <span className="login-form__security">Uçtan uca güvenli bağlantı</span>
      </form>
    </div>
  );
}
