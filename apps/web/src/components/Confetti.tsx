import { useEffect, useRef } from 'react';

const PIECES = 130;
const SHADES = ['#ffffff', '#ececec', '#cfcfcf', '#a8a8a8'];

/**
 * A single celebratory burst behind the result card. Pure canvas, one shot,
 * removes nothing and requests nothing once the last piece has left the
 * screen. Skipped entirely under reduced motion.
 */
export function Confetti() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext('2d');
    if (!canvas || !context) return;
    if (
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches
    )
      return;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const width = window.innerWidth;
    const height = window.innerHeight;
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);

    const pieces = Array.from({ length: PIECES }, () => {
      const angle = -Math.PI / 2 + (Math.random() - 0.5) * 1.5;
      const speed = 420 + Math.random() * 620;
      return {
        x: width / 2 + (Math.random() - 0.5) * width * 0.24,
        y: height * 0.62,
        vx: Math.cos(angle) * speed,
        vy: Math.sin(angle) * speed,
        w: 4 + Math.random() * 6,
        h: 7 + Math.random() * 9,
        spin: (Math.random() - 0.5) * 14,
        rotation: Math.random() * Math.PI,
        shade: SHADES[Math.floor(Math.random() * SHADES.length)],
        drag: 0.985 + Math.random() * 0.012,
      };
    });

    let raf = 0;
    let last = performance.now();
    const started = last;
    const frame = (now: number) => {
      const dt = Math.min((now - last) / 1000, 1 / 30);
      last = now;
      context.setTransform(dpr, 0, 0, dpr, 0, 0);
      context.clearRect(0, 0, width, height);
      let alive = 0;
      const age = (now - started) / 1000;
      const fade = age > 1.6 ? Math.max(0, 1 - (age - 1.6) / 0.6) : 1;
      for (const piece of pieces) {
        piece.vy += 1350 * dt;
        piece.vx *= piece.drag;
        piece.vy *= piece.drag;
        piece.x += piece.vx * dt;
        piece.y += piece.vy * dt;
        piece.rotation += piece.spin * dt;
        if (piece.y > height + 30 || fade === 0) continue;
        alive += 1;
        context.save();
        context.translate(piece.x, piece.y);
        context.rotate(piece.rotation);
        context.globalAlpha = fade * 0.95;
        context.fillStyle = piece.shade;
        context.fillRect(-piece.w / 2, -piece.h / 2, piece.w, piece.h);
        context.restore();
      }
      if (alive > 0) raf = window.requestAnimationFrame(frame);
      else context.clearRect(0, 0, width, height);
    };
    raf = window.requestAnimationFrame(frame);
    return () => window.cancelAnimationFrame(raf);
  }, []);

  return <canvas ref={canvasRef} className="confetti-canvas" aria-hidden="true" />;
}
