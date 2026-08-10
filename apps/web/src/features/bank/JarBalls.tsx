import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

import { telegram } from '../../telegram';
import {
  createFlightField,
  createPile,
  liftSurfaceToken,
  placeSettled,
  pointerRadius,
  pour,
  releaseEscaped,
  resizeFlightField,
  resizePile,
  stepFlyingBalls,
  stepPile,
  targetCount,
  worstOverlap,
} from './jarPhysics';
import type { Ball } from './jarPhysics';
import { startDeviceTilt } from './deviceTilt';

const NEW_TOKEN_INTERVAL = 0.095;
const CHAMBER_LEFT = 0.178;
const CHAMBER_RIGHT = 0.178;
const CHAMBER_TOP = 0.185;
const CHAMBER_BOTTOM = 0.075;
const IDLE_EJECTION_MIN = 18;
const IDLE_EJECTION_SPREAD = 10;

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
  const flightCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const [flightHost, setFlightHost] = useState<HTMLElement | null>(null);
  const fillRef = useRef(fill);

  useLayoutEffect(() => {
    setFlightHost(canvasRef.current?.closest<HTMLElement>('.screen-stage') ?? null);
  }, []);

  useEffect(() => {
    fillRef.current = fill;
  }, [fill]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const flightCanvas = flightCanvasRef.current;
    const context = canvas?.getContext('2d');
    const flightContext = flightCanvas?.getContext('2d');
    if (!canvas || !flightCanvas || !context || !flightContext) return;

    const reducedMotion =
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    const pile = createPile(0, 0);
    const flight = createFlightField(0, 0, 0, 0, 0, 0);
    const gramDiamond = new Path2D(GRAM_DIAMOND_PATH);
    const gramSpark = new Path2D(GRAM_SPARK_PATH);
    let dpr = 1;
    let raf = 0;
    let pourClock = 0;
    let idleEjectionClock = IDLE_EJECTION_MIN + Math.random() * IDLE_EJECTION_SPREAD;
    let stageWidth = 0;
    let stageHeight = 0;
    let flightWidth = 0;
    let flightHeight = 0;
    let chamberLeft = 0;
    let chamberTop = 0;
    let flightChamberLeft = 0;
    let flightChamberTop = 0;

    const resize = () => {
      const box = canvas.getBoundingClientRect();
      const flightBox = flightCanvas.getBoundingClientRect();
      if (!box.width || !box.height || !flightBox.width || !flightBox.height) return;
      const previousFlightWidth = flightWidth;
      const previousFlightHeight = flightHeight;
      const previousWidth = pile.width;
      const previousHeight = pile.height;
      stageWidth = box.width;
      stageHeight = box.height;
      flightWidth = flightBox.width;
      flightHeight = flightBox.height;
      chamberLeft = stageWidth * CHAMBER_LEFT;
      chamberTop = stageHeight * CHAMBER_TOP;
      const chamberWidth = stageWidth * (1 - CHAMBER_LEFT - CHAMBER_RIGHT);
      const chamberHeight = stageHeight * (1 - CHAMBER_TOP - CHAMBER_BOTTOM);
      flightChamberLeft = box.left - flightBox.left + chamberLeft;
      flightChamberTop = box.top - flightBox.top + chamberTop;
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.round(stageWidth * dpr);
      canvas.height = Math.round(stageHeight * dpr);
      flightCanvas.width = Math.round(flightWidth * dpr);
      flightCanvas.height = Math.round(flightHeight * dpr);
      resizePile(pile, chamberWidth, chamberHeight);
      resizeFlightField(
        flight,
        flightWidth,
        flightHeight,
        flightChamberLeft,
        flightChamberTop,
        chamberWidth,
        chamberHeight,
      );

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
      if (flight.balls.length && previousFlightWidth > 0 && previousFlightHeight > 0) {
        const scaleX = flightWidth / previousFlightWidth;
        const scaleY = flightHeight / previousFlightHeight;
        for (const ball of flight.balls) {
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
    const stampGram = (target: CanvasRenderingContext2D, ball: Ball, x: number, y: number) => {
      target.save();
      target.translate(x, y);
      target.rotate(ball.angle);
      // Tokens turn freely in the screen plane, but the stamp never collapses
      // into an edge-on line: at this size that reads as a broken logo.
      target.globalAlpha = 0.62;
      const markScale = (ball.r * 1.16) / 100;
      target.scale(markScale, markScale);
      target.translate(-50, -52);
      target.fillStyle = 'rgba(10, 10, 10, 0.82)';
      target.fill(gramDiamond);
      target.fillStyle = 'rgba(255, 255, 255, 0.92)';
      target.fill(gramSpark);
      target.restore();
    };

    const drawToken = (
      target: CanvasRenderingContext2D,
      ball: Ball,
      x: number,
      y: number,
      lightWidth: number,
      lightHeight: number,
    ) => {
      // One light source belongs to the whole jar. Material variation is kept
      // deliberately narrow; it stops the GRAMчики looking cloned without
      // reverting to the old random checkerboard of unrelated shades.
      const lightX = lightWidth ? 1 - x / lightWidth : 0.5;
      const lightY = lightHeight ? 1 - y / lightHeight : 0.5;
      const grey = Math.round(151 + lightX * 45 + lightY * 12 + ball.material * 10);

      target.beginPath();
      target.arc(x, y, ball.r, 0, Math.PI * 2);
      target.fillStyle = `rgb(${grey}, ${grey}, ${grey})`;
      target.globalAlpha = 0.96;
      target.fill();

      target.beginPath();
      target.arc(x - ball.r * 0.08, y - ball.r * 0.08, ball.r * 0.78, 3.55, 5.2);
      target.lineWidth = Math.max(0.55, ball.r * 0.075);
      target.strokeStyle = 'rgba(255, 255, 255, 0.32)';
      target.stroke();

      target.beginPath();
      target.arc(x + ball.r * 0.08, y + ball.r * 0.08, ball.r * 0.82, 0.15, 1.78);
      target.lineWidth = Math.max(0.65, ball.r * 0.1);
      target.strokeStyle = 'rgba(0, 0, 0, 0.28)';
      target.stroke();

      stampGram(target, ball, x, y);
    };

    const draw = () => {
      context.setTransform(dpr, 0, 0, dpr, 0, 0);
      context.clearRect(0, 0, stageWidth, stageHeight);
      flightContext.setTransform(dpr, 0, 0, dpr, 0, 0);
      flightContext.clearRect(0, 0, flightWidth, flightHeight);
      // Tokens lower in the pile sit visually in front of those above them.
      // Sorting only the draw order does not interfere with the physics.
      for (const ball of [...pile.balls].sort((a, b) => a.y - b.y)) {
        drawToken(
          context,
          ball,
          chamberLeft + ball.x,
          chamberTop + ball.y,
          stageWidth,
          stageHeight,
        );
      }
      for (const ball of [...flight.balls].sort((a, b) => a.y - b.y)) {
        drawToken(flightContext, ball, ball.x, ball.y, flightWidth, flightHeight);
      }
      context.globalAlpha = 1;
      flightContext.globalAlpha = 1;
      canvas.dataset.ballCount = String(pile.balls.length + flight.balls.length);
      canvas.dataset.insideCount = String(pile.balls.length);
      canvas.dataset.flyingCount = String(flight.balls.length);
      canvas.dataset.targetCount = String(targetCount(pile, fillRef.current));
      flightCanvas.dataset.flyingCount = String(flight.balls.length);
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

    const simulate = (dt: number) => {
      const target = targetCount(pile, fillRef.current);
      const total = pile.balls.length + flight.balls.length;
      if (total > target) {
        const excess = total - target;
        const fromPile = Math.min(excess, pile.balls.length);
        pile.balls.length -= fromPile;
        if (excess > fromPile) flight.balls.length -= excess - fromPile;
      } else if (total < target) {
        pourClock += dt;
        if (pourClock >= NEW_TOKEN_INTERVAL) {
          pour(pile, fillRef.current, Math.random, 1, flight.balls.length);
          pourClock = 0;
        }
      } else {
        pourClock = 0;
      }

      // The jar is alive, not boiling: only one surface token gets a gentle
      // breath every 18–28 seconds, and only when the jar is at least a third
      // full, untouched and upright. Pointer and device tilt remain physical.
      if (
        !reducedMotion &&
        fillRef.current >= 30 &&
        flight.balls.length === 0 &&
        pile.pointer === null &&
        pile.gravity.y > 0.72
      ) {
        idleEjectionClock -= dt;
        if (idleEjectionClock <= 0) {
          liftSurfaceToken(pile);
          idleEjectionClock = IDLE_EJECTION_MIN + Math.random() * IDLE_EJECTION_SPREAD;
        }
      } else {
        idleEjectionClock = Math.max(idleEjectionClock, 3);
      }

      stepPile(pile, dt);
      releaseEscaped(pile, flight, flightChamberLeft, flightChamberTop);
      stepFlyingBalls(flight, pile, flightChamberLeft, flightChamberTop, pile.gravity, dt);
      draw();
    };

    let last = performance.now();
    const frame = (now: number) => {
      const dt = Math.min((now - last) / 1000, 1 / 30);
      last = now;
      simulate(dt);
      raf = window.requestAnimationFrame(frame);
    };

    // The jar is a button and the chamber above the canvas takes no pointer
    // events, so the cursor is tracked on the window and converted to canvas
    // coordinates. That also lets the balls react while the cursor merely
    // passes over the glass, which is the whole point of the effect.
    const trackPointer = (event: PointerEvent) => {
      if (reducedMotion || !pile.width) return;
      const box = canvas.getBoundingClientRect();
      const x = event.clientX - box.left - chamberLeft;
      const y = event.clientY - box.top - chamberTop;
      const radius = pointerRadius(pile.width);
      const outside =
        x < -radius || y < -radius || x > box.width + radius || y > box.height + radius;
      pile.pointer = outside ? null : { x, y, radius };
    };
    const dropPointer = () => {
      pile.pointer = null;
    };
    // A finger leaving the glass is gone; a mouse button coming back up is not,
    // and clearing on it would kill the effect for everyone who taps the jar.
    const releasePointer = (event: PointerEvent) => {
      if (event.pointerType !== 'mouse') dropPointer();
    };
    window.addEventListener('pointermove', trackPointer, { passive: true });
    window.addEventListener('pointerdown', trackPointer, { passive: true });
    window.addEventListener('pointerup', releasePointer, { passive: true });
    window.addEventListener('pointercancel', dropPointer, { passive: true });
    window.addEventListener('blur', dropPointer);

    type JarDebugWindow = Window & {
      advanceTime?: (milliseconds: number) => void;
      render_game_to_text?: () => string;
    };
    const debugWindow = window as JarDebugWindow;
    const renderJarState = () => {
      const mouthTokens = pile.balls.filter(
        (ball) => ball.x - ball.r >= pile.mouth.left && ball.x + ball.r <= pile.mouth.right,
      );
      const insideCentroid = pile.balls.reduce(
        (total, ball) => ({ x: total.x + ball.x, y: total.y + ball.y }),
        { x: 0, y: 0 },
      );
      const highestMouthToken = mouthTokens.reduce<(typeof mouthTokens)[number] | null>(
        (highest, ball) => (!highest || ball.y < highest.y ? ball : highest),
        null,
      );
      const smallestRadius = pile.balls.reduce(
        (smallest, ball) => Math.min(smallest, ball.r),
        Number.POSITIVE_INFINITY,
      );
      const overlap = worstOverlap(pile);
      return JSON.stringify({
        coordinateSystem: 'BANK screen-stage origin top-left; x right; y down; pixels',
        fillPercent: fillRef.current,
        stage: { width: flightWidth, height: flightHeight },
        jarStage: {
          left: Number((flightChamberLeft - chamberLeft).toFixed(2)),
          top: Number((flightChamberTop - chamberTop).toFixed(2)),
          width: Number(stageWidth.toFixed(2)),
          height: Number(stageHeight.toFixed(2)),
        },
        gravity: {
          x: Number(pile.gravity.x.toFixed(3)),
          y: Number(pile.gravity.y.toFixed(3)),
        },
        mouth: { left: flight.mouthLeft, right: flight.mouthRight, y: flight.mouthY },
        jarBottom: Number(flight.jarBottom.toFixed(2)),
        inside: pile.balls.length,
        worstOverlap: Number(overlap.toFixed(3)),
        overlapRatio: Number.isFinite(smallestRadius)
          ? Number((overlap / smallestRadius).toFixed(3))
          : 0,
        insideCentroid: pile.balls.length
          ? {
              x: Number((flightChamberLeft + insideCentroid.x / pile.balls.length).toFixed(2)),
              y: Number((flightChamberTop + insideCentroid.y / pile.balls.length).toFixed(2)),
            }
          : null,
        highestMouthToken: highestMouthToken
          ? {
              x: Number((highestMouthToken.x + flightChamberLeft).toFixed(2)),
              y: Number((highestMouthToken.y + flightChamberTop).toFixed(2)),
              vy: Number(highestMouthToken.vy.toFixed(2)),
              r: Number(highestMouthToken.r.toFixed(2)),
            }
          : null,
        flying: flight.balls.map((ball) => ({
          x: Number(ball.x.toFixed(2)),
          y: Number(ball.y.toFixed(2)),
          vx: Number(ball.vx.toFixed(2)),
          vy: Number(ball.vy.toFixed(2)),
          r: Number(ball.r.toFixed(2)),
        })),
        target: targetCount(pile, fillRef.current),
      });
    };
    const debugEject = (event: KeyboardEvent) => {
      if (event.code !== 'Space') return;
      event.preventDefault();
      liftSurfaceToken(pile, () => 0.72);
    };
    if (import.meta.env.VITE_MOCK_TELEGRAM === 'true') {
      debugWindow.render_game_to_text = renderJarState;
      debugWindow.advanceTime = (milliseconds: number) => {
        const frames = Math.max(1, Math.ceil(milliseconds / (1000 / 60)));
        for (let index = 0; index < frames; index += 1) simulate(1 / 60);
      };
      if (!reducedMotion) window.addEventListener('keydown', debugEject);
    }

    const observer =
      typeof ResizeObserver !== 'undefined' ? new ResizeObserver(() => resize()) : null;
    observer?.observe(canvas);
    observer?.observe(flightCanvas);

    const app = telegram();
    const tilt = startDeviceTilt(app, (gravity) => {
      pile.gravity.x = gravity.x;
      pile.gravity.y = gravity.y;
    });
    const requestTiltPermission = (event: PointerEvent) => {
      const target = event.target;
      if (target instanceof Element && target.closest('.bank-object')) {
        void tilt.requestPermission();
      }
    };
    window.addEventListener('pointerdown', requestTiltPermission, { passive: true });

    // Reduced Motion removes the autonomous ejection and pointer disturbance,
    // not direct physical input. A user rotating the phone must still move the
    // tokens, so the lightweight solver keeps running on every device.
    settleInitialFill();
    raf = window.requestAnimationFrame(frame);

    return () => {
      window.cancelAnimationFrame(raf);
      window.removeEventListener('pointermove', trackPointer);
      window.removeEventListener('pointerdown', trackPointer);
      window.removeEventListener('pointerup', releasePointer);
      window.removeEventListener('pointercancel', dropPointer);
      window.removeEventListener('blur', dropPointer);
      window.removeEventListener('pointerdown', requestTiltPermission);
      window.removeEventListener('keydown', debugEject);
      if (debugWindow.render_game_to_text === renderJarState) {
        delete debugWindow.render_game_to_text;
        delete debugWindow.advanceTime;
      }
      observer?.disconnect();
      tilt.stop();
    };
  }, [flightHost]);

  return (
    <>
      <canvas ref={canvasRef} className="bank-ball-canvas" aria-hidden="true" />
      {flightHost &&
        createPortal(
          <canvas ref={flightCanvasRef} className="bank-flight-canvas" aria-hidden="true" />,
          flightHost,
        )}
    </>
  );
}
