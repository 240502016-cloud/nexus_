/**
 * Temaya bağlı, DOM ve Web Audio gerektiren etkiler.
 *
 * CSS ile anlatılamayan iki şey burada: Feline'in tok tıklama sesi ve
 * Silent Ink'in hanko mührü. İkisi de yalnız kendi teması etkinken çalışır.
 */

import type { ThemeMode } from "./settings";

/* --------------------------------------------------------------------------
   Feline — tok tıklama
   Örnek ses dosyası yok: 200 Hz alçak geçiren filtreden geçirilmiş çok kısa bir
   gürültü patlaması sentezleniyor. "Meow" değil; bir kedinin patisinin ahşaba
   değmesi gibi tok ve alçak.
   -------------------------------------------------------------------------- */

let audioContext: AudioContext | null = null;

function context(): AudioContext | null {
  if (typeof window === "undefined") return null;
  if (!audioContext) {
    try {
      audioContext = new AudioContext();
    } catch {
      return null;
    }
  }
  if (audioContext.state === "suspended") void audioContext.resume().catch(() => {});
  return audioContext;
}

/** 40 ms, 200 Hz alçak geçiren, kısık seviyeli tok bir tık. */
function playThock(): void {
  const ctx = context();
  if (!ctx) return;

  const duration = 0.04;
  const frames = Math.floor(ctx.sampleRate * duration);
  const buffer = ctx.createBuffer(1, frames, ctx.sampleRate);
  const data = buffer.getChannelData(0);
  for (let i = 0; i < frames; i += 1) {
    // Hızla sönen gürültü — vuruşun gövdesi filtreden gelir.
    data[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / frames, 3);
  }

  const source = ctx.createBufferSource();
  source.buffer = buffer;

  const lowpass = ctx.createBiquadFilter();
  lowpass.type = "lowpass";
  lowpass.frequency.value = 200;
  lowpass.Q.value = 0.9;

  const gain = ctx.createGain();
  // Kısık tutuluyor: sesli sohbette mikrofona sızmamalı.
  gain.gain.setValueAtTime(0.14, ctx.currentTime);
  gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + duration);

  source.connect(lowpass);
  lowpass.connect(gain);
  gain.connect(ctx.destination);
  source.start();
  source.stop(ctx.currentTime + duration);
}

/* --------------------------------------------------------------------------
   Silent Ink — hanko mührü
   Bir eylem onaylandığında sağ alt köşede kırmızı mühür basılır ve söner.
   -------------------------------------------------------------------------- */

let stampNode: HTMLDivElement | null = null;
let stampTimer = 0;

/** Onaylanan bir eylemden sonra hanko mührünü bir kez bas. */
export function stampHanko(): void {
  if (document.documentElement.getAttribute("data-theme") !== "ink") return;
  if (!stampNode) {
    stampNode = document.createElement("div");
    stampNode.className = "hanko-stamp";
    stampNode.setAttribute("aria-hidden", "true");
    document.body.appendChild(stampNode);
  }
  stampNode.classList.remove("hanko-stamp--on");
  // Sınıfı yeniden eklemeden önce reflow: aynı animasyon üst üste tetiklenebilsin.
  void stampNode.offsetWidth;
  stampNode.classList.add("hanko-stamp--on");
  window.clearTimeout(stampTimer);
  stampTimer = window.setTimeout(() => {
    stampNode?.classList.remove("hanko-stamp--on");
  }, 900);
}

/* --------------------------------------------------------------------------
   Kurulum
   -------------------------------------------------------------------------- */

/**
 * Tıklama sesini bağlar. Yalnız Feline temasında ve yalnız gerçek kontrollerde
 * (buton, sekme, kanal satırı) çalışır; metin seçmek veya sohbeti kaydırmak
 * ses çıkarmaz.
 *
 * Dönen fonksiyon dinleyiciyi kaldırır.
 */
export function installThemeEffects(getTheme: () => ThemeMode, enabled: () => boolean): () => void {
  function onPointerDown(event: PointerEvent) {
    if (getTheme() !== "feline" || !enabled()) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const target = event.target as HTMLElement | null;
    if (!target?.closest("button, [role='button'], [role='tab'], .channel-item, .server-icon")) {
      return;
    }
    playThock();
  }

  document.addEventListener("pointerdown", onPointerDown, { passive: true });
  return () => document.removeEventListener("pointerdown", onPointerDown);
}
