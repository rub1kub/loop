import { useEffect, useRef } from 'react';

import { type CelebrationKind, onCelebrate } from '../celebrate';

const SHADES = ['#ffffff', '#ececec', '#cfcfcf', '#a8a8a8'];

interface Piece {
  x: number;
  y: number;
  vx: number;
  vy: number;
  w: number;
  h: number;
  spin: number;
  rotation: number;
  shade: string;
  drag: number;
  born: number;
  life: number;
}

/**
 * One canvas for every celebration in the app, mounted once and driven by
 * `celebrate()`. Keeping it single means overlapping bursts share a frame loop
 * and the loop stops the moment the last piece is gone, rather than each
 * moment carrying its own canvas.
 */
export function Celebration() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext('2d');
    if (!canvas || !context) return;

    const reducedMotion =
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reducedMotion) return;

    let width = 0;
    let height = 0;
    let dpr = 1;
    const resize = () => {
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      width = window.innerWidth;
      height = window.innerHeight;
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
    };
    resize();
    window.addEventListener('resize', resize);

    const pieces: Piece[] = [];
    let raf = 0;
    let last = performance.now();

    const spawn = (kind: CelebrationKind) => {
      const count = kind === 'burst' ? 130 : 46;
      const power = kind === 'burst' ? 1 : 0.68;
      const now = performance.now();
      for (let i = 0; i < count; i += 1) {
        const angle = -Math.PI / 2 + (Math.random() - 0.5) * 1.5;
        const speed = (420 + Math.random() * 620) * power;
        pieces.push({
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
          born: now,
          life: kind === 'burst' ? 2200 : 1500,
        });
      }
      if (!raf) {
        last = performance.now();
        raf = window.requestAnimationFrame(frame);
      }
    };

    function frame(now: number) {
      const dt = Math.min((now - last) / 1000, 1 / 30);
      last = now;
      context!.setTransform(dpr, 0, 0, dpr, 0, 0);
      context!.clearRect(0, 0, width, height);
      for (let i = pieces.length - 1; i >= 0; i -= 1) {
        const piece = pieces[i];
        const age = now - piece.born;
        piece.vy += 1350 * dt;
        piece.vx *= piece.drag;
        piece.vy *= piece.drag;
        piece.x += piece.vx * dt;
        piece.y += piece.vy * dt;
        piece.rotation += piece.spin * dt;
        const fade =
          age > piece.life * 0.7
            ? Math.max(0, 1 - (age - piece.life * 0.7) / (piece.life * 0.3))
            : 1;
        if (piece.y > height + 30 || fade === 0) {
          pieces.splice(i, 1);
          continue;
        }
        context!.save();
        context!.translate(piece.x, piece.y);
        context!.rotate(piece.rotation);
        context!.globalAlpha = fade * 0.95;
        context!.fillStyle = piece.shade;
        context!.fillRect(-piece.w / 2, -piece.h / 2, piece.w, piece.h);
        context!.restore();
      }
      if (pieces.length > 0) {
        raf = window.requestAnimationFrame(frame);
      } else {
        context!.clearRect(0, 0, width, height);
        raf = 0;
      }
    }

    const stop = onCelebrate(spawn);
    return () => {
      stop();
      window.removeEventListener('resize', resize);
      if (raf) window.cancelAnimationFrame(raf);
    };
  }, []);

  return <canvas ref={canvasRef} className="confetti-canvas" aria-hidden="true" />;
}
