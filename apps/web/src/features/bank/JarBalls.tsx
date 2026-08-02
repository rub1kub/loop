import { useEffect, useRef } from 'react';

import { telegram } from '../../telegram';
import { createPile, pour, stepPile, targetCount } from './jarPhysics';

const SHADES = ['#f2f2f2', '#d8d8d8', '#b9b9b9', '#969696', '#7a7a7a'];

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

    const pile = createPile(0, 0);
    let dpr = 1;
    let raf = 0;

    const resize = () => {
      const box = canvas.getBoundingClientRect();
      if (!box.width || !box.height) return;
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      pile.width = box.width;
      pile.height = box.height;
      canvas.width = Math.round(pile.width * dpr);
      canvas.height = Math.round(pile.height * dpr);
    };
    resize();

    const draw = () => {
      context.setTransform(dpr, 0, 0, dpr, 0, 0);
      context.clearRect(0, 0, pile.width, pile.height);
      for (const ball of pile.balls) {
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
      pile.balls.length = 0;
      for (let i = 0; i < 400 && pile.balls.length < targetCount(pile, fillRef.current); i += 1) {
        pour(pile, fillRef.current, SHADES);
      }
      const sorted = [...pile.balls];
      let x = 0;
      let y = pile.height;
      let rowHeight = 0;
      for (const ball of sorted) {
        if (x + ball.r * 2 > pile.width) {
          x = 0;
          y -= rowHeight * 1.72;
          rowHeight = 0;
        }
        ball.x = x + ball.r;
        ball.y = y - ball.r;
        ball.px = ball.x;
        ball.py = ball.y;
        x += ball.r * 2;
        rowHeight = Math.max(rowHeight, ball.r);
      }
      draw();
    };

    let last = performance.now();
    const frame = (now: number) => {
      const dt = Math.min((now - last) / 1000, 1 / 30);
      last = now;
      pour(pile, fillRef.current, SHADES);
      stepPile(pile, dt);
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
        pile.gravity.x = 0;
        pile.gravity.y = 1;
        return;
      }
      pile.gravity.x = gx / Math.max(magnitude, 1);
      pile.gravity.y = gy / Math.max(magnitude, 1);
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
