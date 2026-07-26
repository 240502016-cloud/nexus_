import { useState } from "react";
import type { ChangeEvent, FormEvent } from "react";

import { ApiError, coreApi } from "../api/client";
import type { User } from "../types";

interface AccountSettingsProps {
  currentUser: User;
  onUserUpdated: (user: User) => void;
}

// Seçilen görseli merkezden kare kırpıp 256px'e küçültür ve JPEG blob döndürür (optimizasyon).
function cropToSquare(file: File, size = 256): Promise<Blob> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    const url = URL.createObjectURL(file);
    img.onload = () => {
      URL.revokeObjectURL(url);
      const side = Math.min(img.width, img.height);
      const sx = (img.width - side) / 2;
      const sy = (img.height - side) / 2;
      const canvas = document.createElement("canvas");
      canvas.width = size;
      canvas.height = size;
      const ctx = canvas.getContext("2d");
      if (!ctx) {
        reject(new Error("Canvas desteklenmiyor"));
        return;
      }
      ctx.drawImage(img, sx, sy, side, side, 0, 0, size, size);
      canvas.toBlob(
        (blob) => (blob ? resolve(blob) : reject(new Error("Görsel dönüştürülemedi"))),
        "image/jpeg",
        0.9,
      );
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("Görsel okunamadı"));
    };
    img.src = url;
  });
}

function avatarInitial(user: User): string {
  return (user.display_name ?? user.username).trim().charAt(0).toUpperCase() || "?";
}

export function AccountSettings({ currentUser, onUserUpdated }: AccountSettingsProps) {
  const [displayName, setDisplayName] = useState(currentUser.display_name ?? "");
  const [savingProfile, setSavingProfile] = useState(false);
  const [profileMsg, setProfileMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const [avatarUrl, setAvatarUrl] = useState<string | null>(currentUser.avatar_url);
  const [uploading, setUploading] = useState(false);
  const [avatarMsg, setAvatarMsg] = useState<{ ok: boolean; text: string } | null>(null);

  async function handleAvatarFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = ""; // aynı dosyayı tekrar seçebilmek için sıfırla
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      setAvatarMsg({ ok: false, text: "Yalnızca görsel dosyaları yüklenebilir." });
      return;
    }
    setAvatarMsg(null);
    setUploading(true);
    try {
      const blob = await cropToSquare(file);
      const updated = await coreApi.uploadAvatar(blob);
      onUserUpdated(updated);
      // Önbelleği atlamak için URL'e sürüm ekle (aynı isimde değil ama yine de garanti).
      setAvatarUrl(updated.avatar_url);
      setAvatarMsg({ ok: true, text: "Profil fotoğrafı güncellendi." });
    } catch (err) {
      setAvatarMsg({ ok: false, text: err instanceof ApiError ? err.message : "Yüklenemedi" });
    } finally {
      setUploading(false);
    }
  }

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [savingPassword, setSavingPassword] = useState(false);
  const [passwordMsg, setPasswordMsg] = useState<{ ok: boolean; text: string } | null>(null);

  async function handleProfileSave(event: FormEvent) {
    event.preventDefault();
    setProfileMsg(null);
    setSavingProfile(true);
    try {
      const trimmed = displayName.trim();
      const updated = await coreApi.updateProfile(trimmed.length > 0 ? trimmed : null);
      onUserUpdated(updated);
      setProfileMsg({ ok: true, text: "Profil güncellendi." });
    } catch (err) {
      setProfileMsg({ ok: false, text: err instanceof ApiError ? err.message : "Güncellenemedi" });
    } finally {
      setSavingProfile(false);
    }
  }

  async function handlePasswordSave(event: FormEvent) {
    event.preventDefault();
    setPasswordMsg(null);
    if (newPassword.length < 8) {
      setPasswordMsg({ ok: false, text: "Yeni parola en az 8 karakter olmalı." });
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordMsg({ ok: false, text: "Yeni parolalar eşleşmiyor." });
      return;
    }
    setSavingPassword(true);
    try {
      await coreApi.changePassword(currentPassword, newPassword);
      setPasswordMsg({ ok: true, text: "Parola değiştirildi." });
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err) {
      setPasswordMsg({ ok: false, text: err instanceof ApiError ? err.message : "Parola değiştirilemedi" });
    } finally {
      setSavingPassword(false);
    }
  }

  return (
    <>
      <div className="settings-panel__section">
        <h3 className="settings-panel__section-title">Hesap bilgileri</h3>
        <div className="avatar-row">
          {avatarUrl ? (
            <img className="avatar-preview" src={avatarUrl} alt="Profil fotoğrafı" />
          ) : (
            <div className="avatar-preview avatar-preview--empty">{avatarInitial(currentUser)}</div>
          )}
          <div className="avatar-row__actions">
            <label className="avatar-upload-btn">
              {uploading ? "Yükleniyor..." : "Fotoğraf yükle"}
              <input
                type="file"
                accept="image/png,image/jpeg,image/webp,image/gif"
                onChange={handleAvatarFile}
                disabled={uploading}
                hidden
              />
            </label>
            <p className="settings-panel__hint">PNG/JPEG/WEBP/GIF, en fazla 2 MB. Kare kırpılır.</p>
            {avatarMsg ? (
              <p className={avatarMsg.ok ? "settings-panel__ok-text" : "settings-panel__error-text"}>
                {avatarMsg.text}
              </p>
            ) : null}
          </div>
        </div>
        <label className="settings-panel__field">
          <span>Kullanıcı adı</span>
          <input value={currentUser.username} disabled />
        </label>
        <label className="settings-panel__field">
          <span>E-posta</span>
          <input value={currentUser.email} disabled />
        </label>
      </div>

      <form className="settings-panel__section" onSubmit={handleProfileSave}>
        <h3 className="settings-panel__section-title">Profil</h3>
        <label className="settings-panel__field">
          <span>Görünen ad</span>
          <input
            value={displayName}
            maxLength={64}
            placeholder={currentUser.username}
            onChange={(e) => setDisplayName(e.target.value)}
          />
        </label>
        {profileMsg ? (
          <p className={profileMsg.ok ? "settings-panel__ok-text" : "settings-panel__error-text"}>
            {profileMsg.text}
          </p>
        ) : null}
        <div className="settings-panel__test-row">
          <button className="settings-panel__save" type="submit" disabled={savingProfile}>
            {savingProfile ? "Kaydediliyor..." : "Profili kaydet"}
          </button>
        </div>
      </form>

      <form className="settings-panel__section" onSubmit={handlePasswordSave}>
        <h3 className="settings-panel__section-title">Parola değiştir</h3>
        <label className="settings-panel__field">
          <span>Mevcut parola</span>
          <input
            type="password"
            value={currentPassword}
            autoComplete="current-password"
            onChange={(e) => setCurrentPassword(e.target.value)}
          />
        </label>
        <label className="settings-panel__field">
          <span>Yeni parola (en az 8 karakter)</span>
          <input
            type="password"
            value={newPassword}
            autoComplete="new-password"
            onChange={(e) => setNewPassword(e.target.value)}
          />
        </label>
        <label className="settings-panel__field">
          <span>Yeni parola (tekrar)</span>
          <input
            type="password"
            value={confirmPassword}
            autoComplete="new-password"
            onChange={(e) => setConfirmPassword(e.target.value)}
          />
        </label>
        {passwordMsg ? (
          <p className={passwordMsg.ok ? "settings-panel__ok-text" : "settings-panel__error-text"}>
            {passwordMsg.text}
          </p>
        ) : null}
        <div className="settings-panel__test-row">
          <button
            className="settings-panel__save"
            type="submit"
            disabled={savingPassword || !currentPassword || !newPassword}
          >
            {savingPassword ? "Değiştiriliyor..." : "Parolayı değiştir"}
          </button>
        </div>
      </form>
    </>
  );
}
