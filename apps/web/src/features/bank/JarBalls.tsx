import { useEffect, useRef } from 'react';

import { telegram } from '../../telegram';
import { createPile, placeSettled, pour, stepPile, targetCount } from './jarPhysics';
import type { Ball } from './jarPhysics';

const NEW_TOKEN_INTERVAL = 0.095;

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
    let pourClock = 0;

    const resize = () => {
      const box = canvas.getBoundingClientRect();
      if (!box.width || !box.height) return;
      const previousWidth = pile.width;
      const previousHeight = pile.height;
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      pile.width = box.width;
      pile.height = box.height;
      canvas.width = Math.round(pile.width * dpr);
      canvas.height = Math.round(pile.height * dpr);

      if (pile.balls.length && previousWidth > 0 && previousHeight > 0) {
        const scaleX = pile.width / previousWidth;
        const scaleY = pile.height / previousHeight;
        for (const ball of pile.balls) {
          ball.x *= scaleX;
          ball.px *= scaleX;
          ball.y *= scaleY;
          ball.py *= scaleY;
          ball.r *= scaleX;
          ball.vx *= scaleX;
          ball.vy *= scaleY;
        }
      }
    };
    resize();

    /**
     * The GRAM diamond, stamped into a ball.
     *
     * Drawn as a path rather than loaded as an image: a ball is a handful of
     * pixels across, and the mark has to stay crisp at any radius and on any
     * pixel ratio. Flat top, point at the bottom, centre seam — the silhouette
     * is what reads at this size, so nothing finer is worth the fill.
     */
    const stampGram = (ball: Ball) => {
      const facing = Math.cos(ball.facePhase);
      const visibility = Math.abs(facing);
      // An almost edge-on engraving becomes a narrow glint instead of an
      // impossibly readable logo. A negative scale naturally mirrors the
      // reverse side and makes part of the pile face away from the viewer.
      if (visibility < 0.14) {
        context.save();
        context.translate(ball.x, ball.y);
        context.rotate(ball.angle);
        context.beginPath();
        context.moveTo(0, -ball.r * 0.48);
        context.lineTo(0, ball.r * 0.48);
        context.lineWidth = Math.max(0.6, ball.r * 0.08);
        context.strokeStyle = 'rgba(255, 255, 255, 0.28)';
        context.stroke();
        context.restore();
        return;
      }

      const s = ball.r * 0.56;
      const top = -s * 0.62;
      context.save();
      context.translate(ball.x, ball.y);
      context.rotate(ball.angle);
      context.scale(facing, 1);
      context.globalAlpha = facing < 0 ? 0.2 + visibility * 0.16 : 0.28 + visibility * 0.28;
      context.beginPath();
      context.moveTo(-s, top);
      context.lineTo(s, top);
      context.lineTo(0, s);
      context.closePath();
      context.fillStyle = 'rgba(0, 0, 0, 0.62)';
      context.fill();
      context.beginPath();
      context.moveTo(0, top);
      context.lineTo(0, s);
      context.lineWidth = Math.max(0.6, ball.r * 0.08);
      context.strokeStyle = 'rgba(255, 255, 255, 0.3)';
      context.stroke();
      context.restore();
    };

    const drawToken = (ball: Ball) => {
      // One light source belongs to the whole jar. Material variation is kept
      // deliberately narrow; it stops the GRAMчики looking cloned without
      // reverting to the old random checkerboard of unrelated shades.
      const lightX = pile.width ? 1 - ball.x / pile.width : 0.5;
      const lightY = pile.height ? 1 - ball.y / pile.height : 0.5;
      const grey = Math.round(151 + lightX * 45 + lightY * 12 + ball.material * 10);

      context.beginPath();
      context.arc(ball.x, ball.y, ball.r, 0, Math.PI * 2);
      context.fillStyle = `rgb(${grey}, ${grey}, ${grey})`;
      context.globalAlpha = 0.96;
      context.fill();

      context.beginPath();
      context.arc(ball.x - ball.r * 0.08, ball.y - ball.r * 0.08, ball.r * 0.78, 3.55, 5.2);
      context.lineWidth = Math.max(0.55, ball.r * 0.075);
      context.strokeStyle = 'rgba(255, 255, 255, 0.32)';
      context.stroke();

      context.beginPath();
      context.arc(ball.x + ball.r * 0.08, ball.y + ball.r * 0.08, ball.r * 0.82, 0.15, 1.78);
      context.lineWidth = Math.max(0.65, ball.r * 0.1);
      context.strokeStyle = 'rgba(0, 0, 0, 0.28)';
      context.stroke();

      stampGram(ball);
    };

    const draw = () => {
      context.setTransform(dpr, 0, 0, dpr, 0, 0);
      context.clearRect(0, 0, pile.width, pile.height);
      // Tokens lower in the pile sit visually in front of those above them.
      // Sorting only the draw order does not interfere with the physics.
      for (const ball of [...pile.balls].sort((a, b) => a.y - b.y)) drawToken(ball);
      context.globalAlpha = 1;
      canvas.dataset.ballCount = String(pile.balls.length);
      canvas.dataset.targetCount = String(targetCount(pile, fillRef.current));
    };

    const settleStatic = () => {
      // Reduced motion: lay the balls out settled, no simulation.
      pile.balls.length = 0;
      for (let i = 0; i < 400 && pile.balls.length < targetCount(pile, fillRef.current); i += 1) {
        pour(pile, fillRef.current);
      }
      placeSettled(pile);
      draw();
    };

    const settleInitialFill = () => {
      const target = targetCount(pile, fillRef.current);
      pour(pile, fillRef.current, Math.random, target);
      // The first frame must tell the truth immediately. Existing progress is
      // pre-settled off-screen; only later confirmed additions enter through
      // the neck and visibly disturb the pile.
      placeSettled(pile);
      draw();
    };

    let last = performance.now();
    const frame = (now: number) => {
      const dt = Math.min((now - last) / 1000, 1 / 30);
      last = now;
      const target = targetCount(pile, fillRef.current);
      if (pile.balls.length > target) {
        pour(pile, fillRef.current, Math.random, 0);
      } else if (pile.balls.length < target) {
        pourClock += dt;
        if (pourClock >= NEW_TOKEN_INTERVAL) {
          pour(pile, fillRef.current, Math.random, 1);
          pourClock = 0;
        }
      } else {
        pourClock = 0;
      }
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
    else {
      settleInitialFill();
      raf = window.requestAnimationFrame(frame);
    }

    return () => {
      window.cancelAnimationFrame(raf);
      observer?.disconnect();
      if (tiltStarted) orientation?.stop();
      app?.offEvent?.('deviceOrientationChanged', onTilt);
    };
  }, []);

  return <canvas ref={canvasRef} className="bank-ball-canvas" aria-hidden="true" />;
}
