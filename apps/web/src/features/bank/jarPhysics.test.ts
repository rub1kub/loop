import { describe, expect, it } from 'vitest';

import { createPile, fastestSpeed, pour, stepPile, worstOverlap } from './jarPhysics';

const SHADES = ['#fff'];
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
    pour(pile, fill, SHADES, random);
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
    pour(pile, 100, SHADES, random);
    expect(pile.balls.length).toBe(3);
  });

  it('drops the surface when the fill falls', () => {
    const pile = settledPile(85);
    const high = Math.min(...pile.balls.map((ball) => ball.y));
    const random = seeded(11);
    for (let frame = 0; frame < 300; frame += 1) {
      pour(pile, 20, SHADES, random);
      stepPile(pile, FRAME);
    }
    expect(Math.min(...pile.balls.map((ball) => ball.y))).toBeGreaterThan(high);
  });
});
