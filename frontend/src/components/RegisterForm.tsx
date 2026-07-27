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
          <span className="login-form__eyebrow">BAĞLAN. ÜRET. PAYLAŞ.</span>
          <h2>Yeni çalışma alanın hazır.</h2>
          <p>Topluluklarını kur, ekibini sesli kanallarda buluştur ve fikirlerini anında paylaş.</p>
        </div>
      </section>
      <form className="login-form" onSubmit={handleSubmit}>
        <span className="login-form__eyebrow">NEXUS'A KATIL</span>
        <h1>Yeni hesap oluştur</h1>
        <p className="login-form__subtitle">Birkaç saniye içinde ekibinle buluş.</p>
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
          E-posta
          <input
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            autoComplete="email"
            placeholder="sen@ornek.com"
          />
        </label>
        <label>
          Parola
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="new-password"
            placeholder="En az 8 karakter"
          />
        </label>
        {error ? <p className="login-form__error">{error}</p> : null}
        <button type="submit" disabled={submitting || !username || !email || !password}>
          {submitting ? "Hesap oluşturuluyor..." : "Kayıt ol"}
        </button>
        <button type="button" className="login-form__link" onClick={onSwitchToLogin}>
          Zaten hesabın var mı? Giriş yap
        </button>
        <span className="login-form__security">Ücretsiz ve güvenli iletişim</span>
      </form>
    </div>
  );
}
