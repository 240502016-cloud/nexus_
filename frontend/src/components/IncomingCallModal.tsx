import { useEffect } from "react";

import type { CallNotice, IncomingCall, OutgoingCall } from "../hooks/useGateway";

/**
 * WebAudio ile basit iki-tonlu zil sesi. Binary ses dosyası gerektirmez (Artifact/CSP dostu)
 * ve çalarken tarayıcının otomatik-oynatma kısıtlarına takılmaz çünkü kullanıcı zaten uygulamayla
 * etkileşimde. Döndürülen fonksiyon zili durdurur.
 */
function startRingtone(): () => void {
  let ctx: AudioContext | null = null;
  try {
    ctx = new AudioContext();
  } catch {
    return () => {};
  }
  const audio = ctx;

  function beep(freq: number, start: number, duration: number) {
    const osc = audio.createOscillator();
    const gain = audio.createGain();
    osc.type = "sine";
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(0.0001, start);
    gain.gain.exponentialRampToValueAtTime(0.18, start + 0.03);
    gain.gain.exponentialRampToValueAtTime(0.0001, start + duration);
    osc.connect(gain);
    gain.connect(audio.destination);
    osc.start(start);
    osc.stop(start + duration + 0.02);
  }

  function ring() {
    const t = audio.currentTime;
    beep(880, t, 0.2);
    beep(988, t + 0.25, 0.2);
  }

  ring();
  const interval = window.setInterval(ring, 2000);

  return () => {
    window.clearInterval(interval);
    void audio.close();
  };
}

interface IncomingCallModalProps {
  call: IncomingCall;
  sound: boolean;
  onAccept: () => void;
  onReject: () => void;
}

export function IncomingCallModal({ call, sound, onAccept, onReject }: IncomingCallModalProps) {
  useEffect(() => {
    if (!sound) return;
    return startRingtone();
  }, [sound]);

  return (
    <div className="call-overlay">
      <div className="call-modal">
        <div className="call-modal__avatar">{call.fromUsername.charAt(0).toUpperCase()}</div>
        <div className="call-modal__title">{call.fromUsername} seni arıyor</div>
        <div className="call-modal__subtitle">🔊 {call.channelName} kanalına davet</div>
        <div className="call-modal__actions">
          <button className="call-btn call-btn--accept" onClick={onAccept}>
            Kabul et
          </button>
          <button className="call-btn call-btn--reject" onClick={onReject}>
            Reddet
          </button>
        </div>
      </div>
    </div>
  );
}

interface OutgoingCallToastProps {
  call: OutgoingCall;
  onCancel: () => void;
}

export function OutgoingCallToast({ call, onCancel }: OutgoingCallToastProps) {
  return (
    <div className="call-toast">
      <span className="call-toast__pulse" />
      <span className="call-toast__text">{call.toUsername} aranıyor…</span>
      <button className="call-toast__cancel" onClick={onCancel}>
        İptal
      </button>
    </div>
  );
}

interface CallNoticeToastProps {
  notice: CallNotice;
  onDismiss: () => void;
}

export function CallNoticeToast({ notice, onDismiss }: CallNoticeToastProps) {
  useEffect(() => {
    const id = window.setTimeout(onDismiss, 4000);
    return () => window.clearTimeout(id);
  }, [notice, onDismiss]);

  return (
    <div className="call-toast call-toast--notice">
      <span className="call-toast__text">{notice.text}</span>
      <button className="call-toast__cancel" onClick={onDismiss}>
        Tamam
      </button>
    </div>
  );
}
