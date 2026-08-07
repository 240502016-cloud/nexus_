import { useEffect, useRef } from "react";

import type { ThemeMode } from "../settings";

interface ThemeStageProps {
  theme: ThemeMode;
  /** Sesli görüşme sürüyor mu. Sürüyorsa animasyon tamamen durur. */
  callActive: boolean;
}

/** Parçacık 3B uzayda yaşar; her karede perspektifle 2B'ye izdüşürülür. */
interface Particle {
  x: number;
  y: number;
  z: number;
  a: number;
}

const PARTICLE_COUNT = 800;
const YAW_PER_FRAME = 0.0005; // rad/kare — spesifikasyondaki kamera hızı
const DEPTH = 1400;

/**
 * Tema arka planının canlı katmanı. Şu an yalnız "space" temasında çizer;
 * diğer temaların dokuları saf CSS olduğu için canvas hiç mount edilmez.
 *
 * NEDEN three.js DEĞİL: spesifikasyon WebGL öneriyor, ancak three.js ~600 kB
 * ve bu uygulama aynı GPU üzerinde WebRTC video kodluyor. 800 parçacığın
 * perspektif izdüşümü ve additive blending'i 2B canvas'ta doğrudan yazılabilir;
 * görsel sonuç aynı, bağımlılık ve GPU baskısı yok.
 *
 * PERFORMANS SÖZLEŞMESİ: döngü şu üç durumda tamamen bırakılır (kare atlamak
 * değil, rAF zincirinden çıkmak): sesli görüşme aktifken, sekme arka plandayken,
 * hareket azaltma tercihi verildiğinde. Sonuncusunda canvas gizlenir ve CSS
 * statik nebula yedeği devreye girer.
 */
export function ThemeStage({ theme, callActive }: ThemeStageProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const callActiveRef = useRef(callActive);
  callActiveRef.current = callActive;

  // Panel spotlight'ı: işaretçi konumu köke yazılır, CSS radial-gradient izler.
  useEffect(() => {
    if (theme !== "space") return;
    let queued = false;
    let px = 0;
    let py = 0;

    function flush() {
      queued = false;
      const root = document.documentElement;
      root.style.setProperty("--mx", `${px}px`);
      root.style.setProperty("--my", `${py}px`);
    }

    function onMove(event: PointerEvent) {
      const target = (event.target as HTMLElement | null)?.closest<HTMLElement>(
        ".settings-panel, .settings-panel--wide, .lab-card, .theme-card",
      );
      if (!target) return;
      const box = target.getBoundingClientRect();
      px = event.clientX - box.left;
      py = event.clientY - box.top;
      // Kare başına en fazla bir yazma; pointermove saniyede yüzlerce kez gelir.
      if (!queued) {
        queued = true;
        requestAnimationFrame(flush);
      }
    }

    window.addEventListener("pointermove", onMove, { passive: true });
    return () => window.removeEventListener("pointermove", onMove);
  }, [theme]);

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
    let particles: Particle[] = [];
    let yaw = 0;
    let running = false;
    let frameId = 0;

    function build() {
      particles = Array.from({ length: PARTICLE_COUNT }, () => ({
        x: (Math.random() - 0.5) * 2600,
        y: (Math.random() - 0.5) * 2600,
        z: Math.random() * DEPTH,
        // Spesifikasyondaki 0.15–0.35 opaklık aralığı.
        a: 0.15 + Math.random() * 0.2,
      }));
    }

    function resize() {
      dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      width = canvas!.clientWidth * dpr;
      height = canvas!.clientHeight * dpr;
      canvas!.width = width;
      canvas!.height = height;
      if (particles.length === 0) build();
    }

    function draw() {
      const styles = getComputedStyle(document.documentElement);
      const ground = styles.getPropertyValue("--bg-app").trim() || "#05060B";
      const nebula = styles.getPropertyValue("--accent").trim() || "#8AA0FF";
      const fore = styles.getPropertyValue("--text-bright").trim() || "#EDEFF7";

      ctx!.globalCompositeOperation = "source-over";
      ctx!.fillStyle = ground;
      ctx!.fillRect(0, 0, width, height);

      const cx = width / 2;
      const cy = height / 2;
      const focal = height * 0.9;
      const cos = Math.cos(yaw);
      const sin = Math.sin(yaw);

      // Additive blending: üst üste binen parçacıklar birikerek nebula yoğunluğu üretir.
      ctx!.globalCompositeOperation = "lighter";

      for (const p of particles) {
        // Kamerayı döndürmek yerine dünyayı ters yönde döndürmek daha ucuz.
        const rx = p.x * cos - p.z * sin;
        const rz = p.z * cos + p.x * sin;
        const depth = rz + DEPTH * 0.35;
        if (depth <= 1) continue;

        const scale = focal / depth;
        const sx = cx + rx * scale;
        const sy = cy + p.y * scale;
        if (sx < -8 || sx > width + 8 || sy < -8 || sy > height + 8) continue;

        // Uzaktakiler küçülür ve söner; yakındakiler nebula rengini alır.
        const near = 1 - depth / (DEPTH * 1.35);
        const radius = Math.max(0.35, scale * 1.5) * dpr;
        ctx!.globalAlpha = p.a * Math.max(0.15, near);
        ctx!.fillStyle = near > 0.55 ? nebula : fore;
        ctx!.beginPath();
        ctx!.arc(sx, sy, radius, 0, Math.PI * 2);
        ctx!.fill();
      }

      ctx!.globalAlpha = 1;
      ctx!.globalCompositeOperation = "source-over";
    }

    const idle = () => document.hidden || callActiveRef.current || reduced.matches;

    function frame() {
      if (idle()) {
        running = false;
        draw();
        return;
      }
      yaw += YAW_PER_FRAME;
      draw();
      frameId = requestAnimationFrame(frame);
    }

    function wake() {
      if (running) return;
      if (idle()) {
        draw();
        return;
      }
      running = true;
      frameId = requestAnimationFrame(frame);
    }

    function handleResize() {
      resize();
      wake();
    }

    resize();
    wake();

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
