import { useEffect, useRef } from "react";

import type { ThemeMode } from "../settings";

interface ThemeStageProps {
  theme: ThemeMode;
  /** Sesli görüşme sürüyor mu. Sürüyorsa animasyon tamamen durur. */
  callActive: boolean;
}

interface Star {
  x: number;
  y: number;
  r: number;
  a: number;
  vx: number;
  vy: number;
}

/**
 * Tema arka planının canlı katmanı.
 *
 * Şu an yalnız "space" temasının yıldız akışını çizer; diğer temaların
 * dokuları saf CSS olduğu için burada iş yapmazlar ve canvas hiç mount edilmez.
 *
 * PERFORMANS SÖZLEŞMESİ — bu proje bir portfolyo sitesi değil, aynı GPU
 * üzerinde WebRTC video kodluyor. Döngü şu üç durumda tamamen bırakılır
 * (kare atlamak değil, `requestAnimationFrame` zincirinden çıkmak):
 *   1. sesli görüşme aktifken
 *   2. sekme arka plandayken
 *   3. kullanıcı hareket azaltma tercihi verdiyse
 */
export function ThemeStage({ theme, callActive }: ThemeStageProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const callActiveRef = useRef(callActive);
  callActiveRef.current = callActive;

  useEffect(() => {
    if (theme !== "space") return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d", { alpha: false });
    if (!ctx) return;

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
    let width = 0;
    let height = 0;
    let dpr = 1;
    let stars: Star[] = [];
    let running = false;
    let frameId = 0;

    const lanes = [
      { x: 0.22, y: 0.18, r: 0.62, phase: 0, speed: 0.000012 },
      { x: 0.80, y: 0.74, r: 0.55, phase: 2.1, speed: -0.000009 },
    ];

    function build() {
      // Alan başına sabit yoğunluk; büyük ekranda kalabalıklaşmaz.
      const count = Math.round(Math.min(120, (width * height) / 26000));
      stars = Array.from({ length: count }, () => {
        const depth = Math.random();
        const layer = depth < 0.45 ? 0.25 : depth < 0.8 ? 0.55 : 1;
        return {
          x: Math.random() * width,
          y: Math.random() * height,
          r: (layer * 0.9 + 0.25) * dpr,
          a: 0.1 + layer * 0.3,
          // Sürüklenme algı eşiğinin altında: birkaç piksel/dakika.
          vx: (0.01 + Math.random() * 0.02) * layer,
          vy: (0.004 + Math.random() * 0.01) * layer,
        };
      });
    }

    function resize() {
      dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      width = canvas!.clientWidth * dpr;
      height = canvas!.clientHeight * dpr;
      canvas!.width = width;
      canvas!.height = height;
      build();
    }

    function draw(time: number) {
      const styles = getComputedStyle(document.documentElement);
      const ground = styles.getPropertyValue("--bg-app").trim() || "#07090F";
      const dust = styles.getPropertyValue("--accent").trim() || "#C77B4E";
      const star = styles.getPropertyValue("--text-bright").trim() || "#E8EAED";

      ctx!.fillStyle = ground;
      ctx!.fillRect(0, 0, width, height);

      // Toz şeritleri ışık EKLEMEZ, ışık EKSİLTİR. Gerçek karanlık nebulalar
      // emisyon değil okültasyondur; panelin arkasını koyulaştırdıkları için
      // metin kontrastı düşmez, artar.
      for (const lane of lanes) {
        const cx = width * lane.x + Math.cos(time * lane.speed + lane.phase) * width * 0.05;
        const cy = height * lane.y + Math.sin(time * lane.speed + lane.phase) * height * 0.04;
        const radius = Math.max(width, height) * lane.r;
        const gradient = ctx!.createRadialGradient(cx, cy, 0, cx, cy, radius);
        gradient.addColorStop(0, "rgba(0,0,0,0.55)");
        gradient.addColorStop(0.55, "rgba(0,0,0,0.22)");
        gradient.addColorStop(1, "rgba(0,0,0,0)");
        ctx!.fillStyle = gradient;
        ctx!.fillRect(0, 0, width, height);
      }

      for (const item of stars) {
        item.x += item.vx;
        item.y += item.vy;
        if (item.x > width + 2) item.x = -2;
        if (item.y > height + 2) item.y = -2;
        ctx!.globalAlpha = item.a;
        // En yakın katman toz rengini alır; derindekiler beyaz kalır.
        ctx!.fillStyle = item.r > 1.4 * dpr ? dust : star;
        ctx!.beginPath();
        ctx!.arc(item.x, item.y, item.r, 0, Math.PI * 2);
        ctx!.fill();
      }
      ctx!.globalAlpha = 1;
    }

    const idle = () => document.hidden || callActiveRef.current || reduced.matches;

    function frame(time: number) {
      if (idle()) {
        running = false;
        draw(time);
        return;
      }
      draw(time);
      frameId = requestAnimationFrame(frame);
    }

    function wake() {
      if (running) return;
      if (idle()) {
        draw(performance.now());
        return;
      }
      running = true;
      frameId = requestAnimationFrame(frame);
    }

    resize();
    wake();

    // Kaldırılabilmesi için adlandırılmış olmalı; anonim fonksiyon sızdırırdı.
    const handleResize = () => {
      resize();
      wake();
    };

    window.addEventListener("resize", handleResize);
    document.addEventListener("visibilitychange", wake);
    reduced.addEventListener("change", wake);

    return () => {
      cancelAnimationFrame(frameId);
      running = false;
      window.removeEventListener("resize", handleResize);
      document.removeEventListener("visibilitychange", wake);
      reduced.removeEventListener("change", wake);
    };
  }, [theme]);

  // Görüşme bitince döngü kendiliğinden uyanmaz; burada dürtüyoruz.
  useEffect(() => {
    if (theme !== "space" || callActive) return;
    const id = window.setTimeout(() => {
      document.dispatchEvent(new Event("visibilitychange"));
    }, 0);
    return () => window.clearTimeout(id);
  }, [callActive, theme]);

  if (theme !== "space") return null;

  return <canvas ref={canvasRef} className="theme-stage" aria-hidden="true" />;
}
