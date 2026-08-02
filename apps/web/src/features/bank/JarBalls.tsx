import { useEffect, useRef } from 'react';

import { telegram } from '../../telegram';
import { createPile, placeSettled, pour, stepPile, targetCount } from './jarPhysics';
import type { Ball } from './jarPhysics';

const NEW_TOKEN_INTERVAL = 0.095;

// Normalized from TON's official Gram Diamond Mark asset. Keeping the original
// paths matters here: the small white spark in the upper-right is what makes a
// GRAM token read as GRAM instead of as the old triangular TON glyph.
const GRAM_DIAMOND_PATH =
  'M66.523 11.333H33.477c-4.401 0-6.601 0-8.592.616a13.792 13.792 0 0 0-4.808 2.625c-1.594 1.341-2.784 3.192-5.164 6.894L4.408 37.81c-1.572 2.446-2.358 3.67-2.572 4.956a6.322 6.322 0 0 0 .362 3.37c.482 1.212 1.51 2.24 3.567 4.296l39.033 39.034c1.821 1.82 2.731 2.731 3.781 3.072.924.3 1.918.3 2.842 0 1.05-.34 1.96-1.251 3.78-3.072l39.035-39.034c2.056-2.056 3.084-3.084 3.566-4.296a6.32 6.32 0 0 0 .362-3.37c-.214-1.287-1-2.51-2.572-4.956L85.087 21.47c-2.38-3.703-3.57-5.554-5.164-6.895a13.792 13.792 0 0 0-4.808-2.625c-1.99-.616-4.191-.616-8.592-.616z';
const GRAM_SPARK_PATH =
  'M60.268 24.224c.537-1.45 2.59-1.45 3.126 0l3.71 10.027a2.2 2.2 0 0 0 1.3 1.3l10.027 3.71c1.451.537 1.451 2.59 0 3.126l-10.027 3.71a2.2 2.2 0 0 0-1.3 1.3l-3.71 10.027c-.537 1.451-2.59 1.451-3.126 0l-3.71-10.027a2.2 2.2 0 0 0-1.3-1.3l-10.027-3.71c-1.451-.537-1.451-2.589 0-3.126l10.027-3.71a2.2 2.2 0 0 0 1.3-1.3l3.71-10.027z';

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
    const gramDiamond = new Path2D(GRAM_DIAMOND_PATH);
    const gramSpark = new Path2D(GRAM_SPARK_PATH);
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

    /** The official GRAM diamond and spark, stamped into a physical token. */
    const stampGram = (ball: Ball) => {
      context.save();
      context.translate(ball.x, ball.y);
      context.rotate(ball.angle);
      // Tokens turn freely in the screen plane, but the stamp never collapses
      // into an edge-on line: at this size that reads as a broken logo.
      context.globalAlpha = 0.62;
      const markScale = (ball.r * 1.16) / 100;
      context.scale(markScale, markScale);
      context.translate(-50, -52);
      context.fillStyle = 'rgba(10, 10, 10, 0.82)';
      context.fill(gramDiamond);
      context.fillStyle = 'rgba(255, 255, 255, 0.92)';
      context.fill(gramSpark);
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
