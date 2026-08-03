import { describe, expect, it } from 'vitest';

import {
  createPile,
  fastestSpeed,
  nominalRadius,
  placeSettled,
  pointerRadius,
  pour,
  stepPile,
  worstOverlap,
} from './jarPhysics';

const FRAME = 1 / 60;

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
  it('comes to rest instead of shivering forever', () => {
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
    expect(Math.max(...pile.balls.map((ball) => Math.abs(ball.angularVelocity)))).toBeLessThan(0.1);
  });

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

  it('keeps balls out of each other and inside the jar', () => {
    const pile = settledPile(85);

    // Overlap is what made them look tangled: a ball sunk into its neighbour
    // is drawn inside it, and the solver keeps flinging the pair apart.
    const smallest = Math.min(...pile.balls.map((ball) => ball.r));
    expect(worstOverlap(pile)).toBeLessThan(smallest * 0.15);

    for (const ball of pile.balls) {
      expect(ball.x).toBeGreaterThanOrEqual(ball.r - 0.01);
      expect(ball.x).toBeLessThanOrEqual(pile.width - ball.r + 0.01);
      expect(ball.y).toBeLessThanOrEqual(pile.height - ball.r + 0.01);
    }
  });

  it('pours the fill in gradually rather than all at once', () => {
    const pile = createPile(200, 260);
    const random = seeded(3);
    pour(pile, 100, random);
    expect(pile.balls.length).toBe(3);
  });

  it('drops the surface when the fill falls', () => {
    const pile = settledPile(85);
    const high = Math.min(...pile.balls.map((ball) => ball.y));
    const random = seeded(11);
    for (let frame = 0; frame < 300; frame += 1) {
      pour(pile, 20, random);
      stepPile(pile, FRAME);
    }
    expect(Math.min(...pile.balls.map((ball) => ball.y))).toBeGreaterThan(high);
  });
});

describe('cursor', () => {
  it('carves a hole and lets the pile close it again', () => {
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
  });

  it('never launches a ball when the cursor sweeps across the jar', () => {
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
  });
});
