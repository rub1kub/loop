import { describe, expect, it } from 'vitest';

import {
  BOTTOM_CORNER_RATIO,
  createFlightField,
  createPile,
  fastestSpeed,
  liftSurfaceToken,
  nominalRadius,
  placeSettled,
  pointerRadius,
  pour,
  releaseEscaped,
  stepFlyingBalls,
  stepPile,
  worstOverlap,
} from './jarPhysics';

const FRAME = 1 / 60;
// Settling a jar takes thousands of solver passes. That is fast on its own and
// slow when sixteen test files share the machine, so the heavy cases say how
// long they may take instead of flaking under load.
const SETTLE_TIMEOUT_MS = 30_000;

/** A deterministic stand-in for Math.random, so a failure is reproducible. */
function seeded(seed: number): () => number {
  let state = seed;
  return () => {
    state = (state * 1103515245 + 12345) % 2147483648;
    return state / 2147483648;
  };
}

function settledPile(fill: number) {
  const pile = createPile(200, 260);
  const random = seeded(7);
  for (let frame = 0; frame < 600; frame += 1) {
    pour(pile, fill, random);
    stepPile(pile, FRAME);
  }
  return pile;
}

describe('jar physics', () => {
  it(
    'comes to rest instead of shivering forever',
    () => {
      const pile = settledPile(62);
      expect(pile.balls.length).toBeGreaterThan(40);

      // Resolving contacts by reflecting velocities left every ball in the pile
      // bouncing a little every frame, and the whole fill visibly trembled. A
      // pile that has stopped must read as stopped.
      expect(fastestSpeed(pile)).toBeLessThan(1);

      const before = pile.balls.map((ball) => ({ x: ball.x, y: ball.y }));
      for (let frame = 0; frame < 120; frame += 1) stepPile(pile, FRAME);
      const travelled = pile.balls.reduce(
        (worst, ball, index) =>
          Math.max(worst, Math.hypot(ball.x - before[index].x, ball.y - before[index].y)),
        0,
      );
      expect(travelled).toBeLessThan(0.5);
      expect(Math.max(...pile.balls.map((ball) => Math.abs(ball.angularVelocity)))).toBeLessThan(
        0.1,
      );
    },
    SETTLE_TIMEOUT_MS,
  );

  it('creates one coherent set of tokens with varied physical orientations', () => {
    const pile = createPile(200, 260);
    pour(pile, 100, seeded(19), 40);

    const baseRadius = nominalRadius(pile.width);
    expect(Math.min(...pile.balls.map((ball) => ball.r))).toBeGreaterThanOrEqual(baseRadius * 0.88);
    expect(Math.max(...pile.balls.map((ball) => ball.r))).toBeLessThanOrEqual(baseRadius * 1.12);
    expect(new Set(pile.balls.map((ball) => ball.angle.toFixed(2))).size).toBeGreaterThan(30);
    expect(new Set(pile.balls.map((ball) => ball.facePhase.toFixed(2))).size).toBeGreaterThan(30);
  });

  it('rotates a moving token instead of keeping its mark screen-aligned', () => {
    const pile = createPile(200, 260);
    pour(pile, 100, seeded(23), 1);
    const ball = pile.balls[0];
    ball.x = 80;
    ball.y = 80;
    ball.px = ball.x;
    ball.py = ball.y;
    ball.vx = 90;
    ball.vy = 0;
    pile.gravity = { x: 0, y: 0 };
    const angle = ball.angle;

    stepPile(pile, FRAME);

    expect(ball.angle).not.toBe(angle);
  });

  it('creates an immediate loose pile without overlaps or a simulated fast-forward', () => {
    const pile = createPile(200, 260);
    const random = seeded(31);
    pour(pile, 62, random, 320);
    placeSettled(pile, random);

    expect(worstOverlap(pile)).toBeLessThan(0.001);
    expect(fastestSpeed(pile)).toBe(0);
    expect(new Set(pile.balls.map((ball) => ball.y.toFixed(1))).size).toBeGreaterThan(20);

    const fullPile = createPile(200, 260);
    const fullRandom = seeded(37);
    pour(fullPile, 100, fullRandom, 320);
    placeSettled(fullPile, fullRandom);
    // At 100% a natural mound may enter the open neck by at most one token.
    expect(Math.min(...fullPile.balls.map((ball) => ball.y - ball.r))).toBeGreaterThanOrEqual(
      -nominalRadius(fullPile.width) * 2,
    );
  });

  it(
    'keeps balls out of each other and inside the jar',
    () => {
      const pile = settledPile(85);

      // Overlap is what made them look tangled: a ball sunk into its neighbour
      // is drawn inside it, and the solver keeps flinging the pair apart.
      const smallest = Math.min(...pile.balls.map((ball) => ball.r));
      expect(worstOverlap(pile)).toBeLessThan(smallest * 0.15);

      for (const ball of pile.balls) {
        expect(ball.x).toBeGreaterThanOrEqual(ball.r - 0.01);
        expect(ball.x).toBeLessThanOrEqual(pile.width - ball.r + 0.01);
        expect(ball.y).toBeLessThanOrEqual(pile.height - ball.r + 0.01);

        const cornerRadius = Math.min(pile.width * BOTTOM_CORNER_RATIO, pile.height * 0.18);
        const cornerX = ball.x < pile.width / 2 ? cornerRadius : pile.width - cornerRadius;
        const cornerY = pile.height - cornerRadius;
        if (ball.y > cornerY && (ball.x < cornerRadius || ball.x > pile.width - cornerRadius)) {
          expect(Math.hypot(ball.x - cornerX, ball.y - cornerY)).toBeLessThanOrEqual(
            cornerRadius - ball.r + 0.01,
          );
        }
      }
    },
    SETTLE_TIMEOUT_MS,
  );

  it(
    'does not interpenetrate after sustained tilt and a direction reversal',
    () => {
      const pile = createPile(214, 277);
      const random = seeded(33);
      pour(pile, 62, random, 320);
      placeSettled(pile, random);

      for (const gravity of [
        { x: 0.58, y: 0.82 },
        { x: -0.58, y: 0.82 },
      ]) {
        pile.gravity = gravity;
        for (let frame = 0; frame < 360; frame += 1) stepPile(pile, FRAME);
        const smallest = Math.min(...pile.balls.map((ball) => ball.r));
        expect(worstOverlap(pile)).toBeLessThan(smallest * 0.15);
      }
    },
    SETTLE_TIMEOUT_MS,
  );

  it('pours the fill in gradually rather than all at once', () => {
    const pile = createPile(200, 260);
    const random = seeded(3);
    pour(pile, 100, random);
    expect(pile.balls.length).toBe(3);
  });

  it('opens only the real neck and keeps the glass shoulders solid', () => {
    const pile = createPile(200, 260);
    pour(pile, 100, seeded(41), 2);
    pile.gravity = { x: 0, y: 0 };

    const shoulderBall = pile.balls[0];
    shoulderBall.x = shoulderBall.r;
    shoulderBall.y = shoulderBall.r;
    shoulderBall.vy = -600;
    const mouthBall = pile.balls[1];
    mouthBall.x = pile.width / 2;
    mouthBall.y = mouthBall.r;
    mouthBall.vy = -600;

    stepPile(pile, FRAME);

    expect(shoulderBall.y).toBeGreaterThanOrEqual(shoulderBall.r - 0.01);
    expect(mouthBall.y).toBeLessThan(mouthBall.r);
  });

  it('lets a surface GRAM token cross the neck as one continuous body', () => {
    for (const [fill, seed] of [
      [30, 7],
      [62, 43],
      [100, 71],
    ] as const) {
      // Matches the live phone chamber closely and covers sparse, current and
      // completely full layouts. Random packing must not decide whether the
      // selected token actually reaches the opening.
      const pile = createPile(214, 277);
      const random = seeded(seed);
      pour(pile, fill, random, 320);
      placeSettled(pile, random);
      const field = createFlightField(332, 374, 59, 69, 214);

      expect(liftSurfaceToken(pile, () => 0.6)).toBe(true);
      let released = 0;
      for (let frame = 0; frame < 180 && released === 0; frame += 1) {
        stepPile(pile, FRAME);
        released += releaseEscaped(pile, field, 59, 69);
      }

      expect(released).toBe(1);
      expect(field.balls).toHaveLength(1);
      expect(field.balls[0].x).toBeGreaterThan(field.mouthLeft);
      expect(field.balls[0].x).toBeLessThan(field.mouthRight);
      expect(field.balls[0].ejecting).toBe(false);
    }
  });

  it(
    'drops the surface when the fill falls',
    () => {
      const pile = settledPile(85);
      const high = Math.min(...pile.balls.map((ball) => ball.y));
      const random = seeded(11);
      for (let frame = 0; frame < 300; frame += 1) {
        pour(pile, 20, random);
        stepPile(pile, FRAME);
      }
      expect(Math.min(...pile.balls.map((ball) => ball.y))).toBeGreaterThan(high);
    },
    SETTLE_TIMEOUT_MS,
  );
});

describe('outside the jar', () => {
  it('lets an idle token travel below the whole jar into the surrounding screen', () => {
    const pile = createPile(200, 260);
    pour(pile, 62, seeded(45), 1);
    const token = pile.balls[0];
    token.y = -token.r - 1;
    token.py = token.y;
    token.ejecting = true;
    token.vy = -290;
    token.angle = 0;
    token.facePhase = 0;
    const field = createFlightField(390, 700, 95, 140, 200);

    expect(releaseEscaped(pile, field, 95, 140)).toBe(1);
    expect(Math.abs(field.balls[0].vx)).toBeGreaterThan(150);

    let travelledBelowJar = false;
    for (let frame = 0; frame < 300 && field.balls.length > 0; frame += 1) {
      stepFlyingBalls(field, pile, 95, 140, { x: 0, y: 1 }, FRAME);
      travelledBelowJar ||= field.balls.some((ball) => ball.y > 140 + pile.height);
    }

    expect(travelledBelowJar).toBe(true);
    expect(field.balls).toHaveLength(1);
    expect(field.balls[0].y).toBeLessThanOrEqual(field.height - field.balls[0].r + 0.01);
  });

  it('never lets a flying GRAM token cross any screen edge', () => {
    const pile = createPile(200, 260);
    pour(pile, 100, seeded(47), 1);
    const source = pile.balls.pop()!;
    const field = createFlightField(300, 400, 50, 80, 200);
    field.balls.push({
      ...source,
      x: source.r + 1,
      y: source.r + 1,
      px: source.r + 1,
      py: source.r + 1,
      vx: -5000,
      vy: -5000,
      flightAge: 0,
    });

    for (let frame = 0; frame < 240; frame += 1) {
      stepFlyingBalls(field, pile, 50, 80, { x: 0.8, y: 0.6 }, FRAME);
      for (const ball of field.balls) {
        expect(ball.x).toBeGreaterThanOrEqual(ball.r - 0.01);
        expect(ball.x).toBeLessThanOrEqual(field.width - ball.r + 0.01);
        expect(ball.y).toBeGreaterThanOrEqual(ball.r - 0.01);
        expect(ball.y).toBeLessThanOrEqual(field.height - ball.r + 0.01);
      }
    }
  });

  it('keeps flying GRAM tokens out of each other', () => {
    const pile = createPile(200, 260);
    pour(pile, 100, seeded(61), 2);
    const [left, right] = pile.balls.splice(0, 2);
    const field = createFlightField(390, 700, 95, 140, 200, 260);
    field.balls.push(
      {
        ...left,
        x: 130,
        y: 470,
        px: 130,
        py: 470,
        vx: 720,
        vy: 0,
        flightAge: 0,
      },
      {
        ...right,
        x: 180,
        y: 470,
        px: 180,
        py: 470,
        vx: -720,
        vy: 0,
        flightAge: 0,
      },
    );

    let closest = Number.POSITIVE_INFINITY;
    for (let frame = 0; frame < 45; frame += 1) {
      stepFlyingBalls(field, pile, 95, 140, { x: 0, y: 0 }, FRAME);
      const distance = Math.hypot(
        field.balls[1].x - field.balls[0].x,
        field.balls[1].y - field.balls[0].y,
      );
      closest = Math.min(closest, distance);
      expect(distance).toBeGreaterThanOrEqual(field.balls[0].r + field.balls[1].r - 0.02);
    }

    expect(closest).toBeLessThan(left.r + right.r + 0.5);
  });

  it('cannot cross the jar side even at extreme speed', () => {
    const pile = createPile(200, 260);
    pour(pile, 100, seeded(67), 1);
    const source = pile.balls.pop()!;
    const field = createFlightField(390, 700, 95, 140, 200, 260);
    field.balls.push({
      ...source,
      x: 40,
      y: 240,
      px: 40,
      py: 240,
      vx: 5000,
      vy: 0,
      flightAge: 0,
    });

    for (let frame = 0; frame < 90; frame += 1) {
      stepFlyingBalls(field, pile, 95, 140, { x: 0, y: 0 }, FRAME);
      const ball = field.balls[0];
      expect(
        ball.x + ball.r <= field.jarLeft + 0.01 || ball.x - ball.r >= field.jarRight - 0.01,
      ).toBe(true);
    }
  });

  it('cannot cross the jar bottom even at extreme speed', () => {
    const pile = createPile(200, 260);
    pour(pile, 100, seeded(71), 1);
    const source = pile.balls.pop()!;
    const field = createFlightField(390, 700, 95, 140, 200, 260);
    field.balls.push({
      ...source,
      x: 195,
      y: 500,
      px: 195,
      py: 500,
      vx: 0,
      vy: -5000,
      flightAge: 0,
    });

    for (let frame = 0; frame < 90; frame += 1) {
      stepFlyingBalls(field, pile, 95, 140, { x: 0, y: 0 }, FRAME);
      const ball = field.balls[0];
      expect(ball.y - ball.r).toBeGreaterThanOrEqual(field.jarBottom - 0.01);
    }
  });

  it('lets a descending token fall back through the mouth', () => {
    const pile = createPile(200, 260);
    pour(pile, 100, seeded(53), 1);
    const source = pile.balls.pop()!;
    const field = createFlightField(300, 400, 50, 80, 200);
    const centre = (field.mouthLeft + field.mouthRight) / 2;
    field.balls.push({
      ...source,
      x: centre,
      y: field.mouthY - source.r - 0.5,
      px: centre,
      py: field.mouthY - source.r - 0.5,
      vx: 0,
      vy: 240,
      flightAge: 0.4,
    });

    const returned = stepFlyingBalls(field, pile, 50, 80, { x: 0, y: 1 }, FRAME);

    expect(returned).toBe(1);
    expect(field.balls).toHaveLength(0);
    expect(pile.balls).toHaveLength(1);
    expect(pile.balls[0].x).toBeCloseTo(100, 1);
  });

  it('bounces at an occupied neck instead of inserting one token into another', () => {
    const pile = createPile(200, 260);
    pour(pile, 100, seeded(59), 1);
    const blocker = pile.balls[0];
    blocker.x = pile.width / 2;
    blocker.y = -blocker.r + 3;
    const field = createFlightField(300, 400, 50, 80, 200);
    const centre = (field.mouthLeft + field.mouthRight) / 2;
    field.balls.push({
      ...blocker,
      x: centre,
      y: field.mouthY - blocker.r - 0.5,
      px: centre,
      py: field.mouthY - blocker.r - 0.5,
      vx: 0,
      vy: 240,
      flightAge: 0.4,
    });

    const returned = stepFlyingBalls(field, pile, 50, 80, { x: 0, y: 1 }, FRAME);

    expect(returned).toBe(0);
    expect(field.balls).toHaveLength(1);
    expect(pile.balls).toHaveLength(1);
    expect(field.balls[0].vy).toBeLessThan(0);
    expect(worstOverlap(pile)).toBe(0);
  });
});

describe('cursor', () => {
  it(
    'carves a hole and lets the pile close it again',
    () => {
      const pile = settledPile(85);
      const radius = pointerRadius(pile.width);
      const spot = { x: pile.width / 2, y: pile.height - radius };
      const inside = () =>
        pile.balls.filter((ball) => Math.hypot(ball.x - spot.x, ball.y - spot.y) < radius).length;

      expect(inside()).toBeGreaterThan(0);

      pile.pointer = { ...spot, radius };
      for (let frame = 0; frame < 30; frame += 1) stepPile(pile, FRAME);

      // Nothing may remain inside the cursor while it is there.
      expect(inside()).toBe(0);
      // The shove is real motion, not a teleport: the pile is visibly alive.
      expect(fastestSpeed(pile)).toBeGreaterThan(1);

      pile.pointer = null;
      // Measured: the disturbance is gone by frame 300 and dead by 450.
      for (let frame = 0; frame < 450; frame += 1) stepPile(pile, FRAME);

      // And once the cursor leaves, the pile settles as if nothing happened.
      expect(fastestSpeed(pile)).toBeLessThan(1);
      const smallest = Math.min(...pile.balls.map((ball) => ball.r));
      expect(worstOverlap(pile)).toBeLessThan(smallest * 0.15);
    },
    SETTLE_TIMEOUT_MS,
  );

  it(
    'never launches a ball when the cursor sweeps across the jar',
    () => {
      const pile = settledPile(62);
      const radius = pointerRadius(pile.width);
      for (let frame = 0; frame < 60; frame += 1) {
        // A full sweep in one second — faster than any hand moves over a phone.
        pile.pointer = { x: (pile.width * frame) / 59, y: pile.height * 0.75, radius };
        stepPile(pile, FRAME);
        for (const ball of pile.balls) {
          expect(ball.x).toBeGreaterThanOrEqual(ball.r - 0.01);
          expect(ball.x).toBeLessThanOrEqual(pile.width - ball.r + 0.01);
          expect(ball.y).toBeLessThanOrEqual(pile.height - ball.r + 0.01);
        }
      }
    },
    SETTLE_TIMEOUT_MS,
  );
});
