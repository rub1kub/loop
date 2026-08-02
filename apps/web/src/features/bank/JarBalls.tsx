import { useEffect, useRef } from 'react';

import { telegram } from '../../telegram';

const MAX_BALLS = 320;
// Balls pack with air between them, so the area budget overshoots the
// nominal fill for the pile's surface to land at the right height.
const PACKING = 1.6;
const SHADES = ['#f2f2f2', '#d8d8d8', '#b9b9b9', '#969696', '#7a7a7a'];

interface Ball {
  x: number;
  y: number;
  vx: number;
  vy: number;
  r: number;
  shade: string;
}

/**
 * The jar's contents: a pit of grey balls that settles like a liquid. Gravity
 * follows the device tilt on phones where Telegram exposes the gyroscope
 * (Bot API 8.0, `DeviceOrientation`, angles in radians), so tipping the phone
 * tips the fill. Everywhere else gravity simply points down.
 */
export function JarBalls({ fill }: { fill: number }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const fillRef = useRef(fill);

  useEffect(() => {
    fillRef.current = fill;
  }, [fill]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext('2d');
    if (!canvas || !context) return;

    const reducedMotion =
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    let width = 0;
    let height = 0;
    let dpr = 1;
    const balls: Ball[] = [];
    const gravity = { x: 0, y: 1 };
    let raf = 0;

    const resize = () => {
      const box = canvas.getBoundingClientRect();
      if (!box.width || !box.height) return;
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      width = box.width;
      height = box.height;
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
    };
    resize();

    const ballRadius = () => {
      const base = Math.max(width, 120) * 0.036;
      return base * (0.82 + Math.random() * 0.42);
    };

    const targetCount = () => {
      if (!width || !height) return 0;
      const fraction = Math.min(100, Math.max(0, fillRef.current)) / 100;
      const avgArea = Math.PI * (Math.max(width, 120) * 0.036) ** 2;
      return Math.min(MAX_BALLS, Math.round((width * height * fraction * PACKING) / avgArea));
    };

    const syncCount = () => {
      const target = targetCount();
      // Poured in a few at a time: spawning the whole fill in one frame packs
      // the drop zone three times over and the overlap resolution blasts the
      // pile out of the jar. A trickle also reads as sand being poured.
      let poured = 0;
      while (balls.length < target && poured < 3) {
        const r = ballRadius();
        balls.push({
          x: width * (0.35 + Math.random() * 0.3),
          y: -r - Math.random() * r * 4,
          vx: (Math.random() - 0.5) * 60,
          vy: 40,
          r,
          shade: SHADES[Math.floor(Math.random() * SHADES.length)],
        });
        poured += 1;
      }
      if (balls.length > target) balls.length = target;
    };

    // Spatial hash keeps pair checks local; ~190 balls stay cheap.
    const collide = () => {
      const cell = Math.max(width, 120) * 0.09;
      const grid = new Map<number, number[]>();
      const key = (cx: number, cy: number) => cy * 4096 + cx;
      balls.forEach((ball, index) => {
        const cx = Math.floor(ball.x / cell);
        const cy = Math.floor(ball.y / cell);
        const bucket = grid.get(key(cx, cy));
        if (bucket) bucket.push(index);
        else grid.set(key(cx, cy), [index]);
      });
      balls.forEach((a, i) => {
        const cx = Math.floor(a.x / cell);
        const cy = Math.floor(a.y / cell);
        for (let gx = cx - 1; gx <= cx + 1; gx += 1) {
          for (let gy = cy - 1; gy <= cy + 1; gy += 1) {
            for (const j of grid.get(key(gx, gy)) ?? []) {
              if (j <= i) continue;
              const b = balls[j];
              const dx = b.x - a.x;
              const dy = b.y - a.y;
              const min = a.r + b.r;
              const sq = dx * dx + dy * dy;
              if (sq >= min * min || sq === 0) continue;
              const dist = Math.sqrt(sq);
              const nx = dx / dist;
              const ny = dy / dist;
              const push = (min - dist) / 2;
              a.x -= nx * push;
              a.y -= ny * push;
              b.x += nx * push;
              b.y += ny * push;
              const rel = (b.vx - a.vx) * nx + (b.vy - a.vy) * ny;
              if (rel < 0) {
                const impulse = rel * 0.55;
                a.vx += nx * impulse;
                a.vy += ny * impulse;
                b.vx -= nx * impulse;
                b.vy -= ny * impulse;
              }
            }
          }
        }
      });
    };

    const step = (dt: number) => {
      const g = 1500;
      for (const ball of balls) {
        ball.vx += gravity.x * g * dt;
        ball.vy += gravity.y * g * dt;
        ball.vx *= 0.995;
        ball.vy *= 0.995;
        ball.x += ball.vx * dt;
        ball.y += ball.vy * dt;
        if (ball.x < ball.r) {
          ball.x = ball.r;
          ball.vx = Math.abs(ball.vx) * 0.35;
        } else if (ball.x > width - ball.r) {
          ball.x = width - ball.r;
          ball.vx = -Math.abs(ball.vx) * 0.35;
        }
        if (ball.y > height - ball.r) {
          ball.y = height - ball.r;
          ball.vy = -Math.abs(ball.vy) * 0.25;
          ball.vx *= 0.92;
        } else if (ball.y < ball.r && gravity.y < 0) {
          ball.y = ball.r;
          ball.vy = Math.abs(ball.vy) * 0.25;
        }
      }
      collide();
      collide();
    };

    const draw = () => {
      context.setTransform(dpr, 0, 0, dpr, 0, 0);
      context.clearRect(0, 0, width, height);
      for (const ball of balls) {
        context.beginPath();
        context.arc(ball.x, ball.y, ball.r, 0, Math.PI * 2);
        context.fillStyle = ball.shade;
        context.globalAlpha = 0.92;
        context.fill();
      }
      context.globalAlpha = 1;
    };

    const settleStatic = () => {
      // Reduced motion: lay the balls out settled, no simulation.
      balls.length = 0;
      for (let i = 0; i < 400 && balls.length < targetCount(); i += 1) syncCount();
      const sorted = [...balls];
      let x = 0;
      let y = height;
      let rowHeight = 0;
      for (const ball of sorted) {
        if (x + ball.r * 2 > width) {
          x = 0;
          y -= rowHeight * 1.72;
          rowHeight = 0;
        }
        ball.x = x + ball.r;
        ball.y = y - ball.r;
        x += ball.r * 2;
        rowHeight = Math.max(rowHeight, ball.r);
      }
      draw();
    };

    let last = performance.now();
    const frame = (now: number) => {
      const dt = Math.min((now - last) / 1000, 1 / 30);
      last = now;
      syncCount();
      step(dt);
      draw();
      raf = window.requestAnimationFrame(frame);
    };

    const observer =
      typeof ResizeObserver !== 'undefined'
        ? new ResizeObserver(() => {
            resize();
            if (reducedMotion) settleStatic();
          })
        : null;
    observer?.observe(canvas);

    const app = telegram();
    const orientation = app?.DeviceOrientation;
    const onTilt = () => {
      if (!orientation?.isStarted) return;
      // beta tips the top edge toward or away, gamma tips left or right;
      // their sines are the screen-plane share of real gravity.
      const gx = Math.sin(orientation.gamma);
      const gy = Math.sin(orientation.beta);
      const magnitude = Math.hypot(gx, gy);
      if (magnitude < 0.12) {
        gravity.x = 0;
        gravity.y = 1;
        return;
      }
      gravity.x = gx / Math.max(magnitude, 1);
      gravity.y = gy / Math.max(magnitude, 1);
    };
    let tiltStarted = false;
    if (!reducedMotion && orientation && app?.isVersionAtLeast?.('8.0')) {
      orientation.start({ refresh_rate: 60 }, (started) => {
        tiltStarted = started;
      });
      app.onEvent?.('deviceOrientationChanged', onTilt);
    }

    if (reducedMotion) settleStatic();
    else raf = window.requestAnimationFrame(frame);

    return () => {
      window.cancelAnimationFrame(raf);
      observer?.disconnect();
      if (tiltStarted) orientation?.stop();
      app?.offEvent?.('deviceOrientationChanged', onTilt);
    };
  }, []);

  return <canvas ref={canvasRef} className="bank-ball-canvas" aria-hidden="true" />;
}
