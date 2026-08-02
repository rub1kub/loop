export const MAX_BALLS = 320;
// Share of the filled region the balls themselves occupy. Circles poured
// loosely settle at roughly 0.80 of the area they cover, so asking for a
// little less than that fills the jar to the brim with nothing forced.
//
// This used to be 1.6 — the reasoning was that air between the balls means you
// need extra ones to reach a given height, but it is the other way round, and
// the jar was asked to hold twice the ball area it has room for. Above about
// two thirds full nothing could separate them: balls sat sunk into each other
// and the solver shoved the whole pile every frame trying to fix it.
export const PACKING = 0.76;

// Contacts are solved by moving balls, never by bouncing them, and each ball's
// velocity is read back from how far it actually moved. A ball resting on the
// pile is pulled down by gravity and pushed back up by its neighbours the same
// distance, so it ends the step having gone nowhere and its velocity comes out
// at zero on its own. Reflecting velocities instead left every ball in the pile
// bouncing a little forever, and the whole fill shivered.
const SUB_STEPS = 2;
const SOLVER_PASSES = 12;
const GRAVITY = 1500;
const DRAG = 0.995;

export interface Ball {
  x: number;
  y: number;
  /** Where the ball started the substep, so the solver can report what it did. */
  px: number;
  py: number;
  vx: number;
  vy: number;
  r: number;
  /** Rotation of the physical token and its engraved mark, in radians. */
  angle: number;
  angularVelocity: number;
  /** A second axis makes some marks face away or appear almost edge-on. */
  facePhase: number;
  faceVelocity: number;
  /** Small material variation; lighting itself is derived from position. */
  material: number;
}

export interface Pile {
  balls: Ball[];
  width: number;
  height: number;
  gravity: { x: number; y: number };
}

export function createPile(width: number, height: number): Pile {
  return { balls: [], width, height, gravity: { x: 0, y: 1 } };
}

export function nominalRadius(width: number): number {
  return Math.max(width, 120) * 0.036;
}

export function targetCount(pile: Pile, fillPercent: number): number {
  if (!pile.width || !pile.height) return 0;
  const fraction = Math.min(100, Math.max(0, fillPercent)) / 100;
  const avgArea = Math.PI * nominalRadius(pile.width) ** 2;
  return Math.min(MAX_BALLS, Math.round((pile.width * pile.height * fraction * PACKING) / avgArea));
}

/**
 * Tops the pile up towards its target, a few balls a frame.
 *
 * Spawning a whole fill at once packs the drop zone several times over, and
 * the solver spends the next second shoving the overlap apart. A trickle also
 * lets each new GRAMчик be noticed. The stream is spread across most of the
 * jar and the drop heights are staggered: down one narrow column, three balls
 * a frame land inside each other and arrive already tangled.
 */
export function pour(
  pile: Pile,
  fillPercent: number,
  random: () => number = Math.random,
  perFrame = 3,
): void {
  const target = targetCount(pile, fillPercent);
  let poured = 0;
  while (pile.balls.length < target && poured < perFrame) {
    // GRAMчики belong to one physical set. A controlled tolerance keeps the pile
    // organic without turning it into unrelated large and small bubbles.
    const r = nominalRadius(pile.width) * (0.88 + random() * 0.24);
    const x = pile.width * (0.2 + random() * 0.6);
    const y = -r - random() * r * 8;
    pile.balls.push({
      x,
      y,
      px: x,
      py: y,
      vx: (random() - 0.5) * 60,
      vy: 40,
      r,
      angle: random() * Math.PI * 2,
      angularVelocity: (random() - 0.5) * 9,
      facePhase: random() * Math.PI * 2,
      faceVelocity: (random() - 0.5) * 2.4,
      material: random() - 0.5,
    });
    poured += 1;
  }
  if (pile.balls.length > target) pile.balls.length = target;
}

/**
 * Places an existing fill as if every token had already fallen vertically.
 *
 * A short physics fast-forward used to do this before the first paint. Apart
 * from blocking slower phones, equal-sized circles had enough simulated time
 * to crystallise into conspicuous diagonal rows. Trying several random drop
 * points per token produces a loose, non-overlapping pile immediately. Live
 * additions still use `pour` and enter through the open top.
 */
export function placeSettled(pile: Pile, random: () => number = Math.random): void {
  const placed: Ball[] = [];
  const order = [...pile.balls].sort((a, b) => b.r - a.r);

  for (const ball of order) {
    let bestX = pile.width / 2;
    let bestY = -Infinity;

    for (let attempt = 0; attempt < 80; attempt += 1) {
      const x = ball.r + random() * Math.max(0, pile.width - ball.r * 2);
      let y = pile.height - ball.r;

      for (const other of placed) {
        const dx = x - other.x;
        const distance = ball.r + other.r;
        if (Math.abs(dx) >= distance) continue;
        const supportY = other.y - Math.sqrt(distance * distance - dx * dx);
        y = Math.min(y, supportY);
      }

      // Greater y is the lower, more stable landing point on canvas.
      if (y > bestY) {
        bestX = x;
        bestY = y;
      }
    }

    ball.x = bestX;
    ball.y = bestY;
    ball.px = bestX;
    ball.py = bestY;
    ball.vx = 0;
    ball.vy = 0;
    ball.angularVelocity = 0;
    ball.faceVelocity = 0;
    placed.push(ball);
  }
}

type Grid = Map<number, number[]>;

const cellKey = (cx: number, cy: number) => cy * 4096 + cx;

/**
 * Spatial hash so each ball only tests its neighbours.
 *
 * Built once per substep and reused across every solver pass: a ball moves at
 * most a fraction of its radius in a substep and the corrections are smaller
 * still, so the three-by-three neighbourhood it lands in stays correct. Rebuilt
 * per pass instead, the passes needed to settle a deep pile cost several times
 * as much for the same answer.
 */
function buildGrid(pile: Pile): { grid: Grid; cell: number } {
  const cell = Math.max(pile.width, 120) * 0.09;
  const grid: Grid = new Map();
  pile.balls.forEach((ball, index) => {
    const key = cellKey(Math.floor(ball.x / cell), Math.floor(ball.y / cell));
    const bucket = grid.get(key);
    if (bucket) bucket.push(index);
    else grid.set(key, [index]);
  });
  return { grid, cell };
}

function solveContacts(pile: Pile, grid: Grid, cell: number): void {
  const { balls } = pile;
  balls.forEach((a, i) => {
    const cx = Math.floor(a.x / cell);
    const cy = Math.floor(a.y / cell);
    for (let gx = cx - 1; gx <= cx + 1; gx += 1) {
      for (let gy = cy - 1; gy <= cy + 1; gy += 1) {
        for (const j of grid.get(cellKey(gx, gy)) ?? []) {
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
        }
      }
    }
  });
}

function solveWalls(pile: Pile): void {
  const { balls, width, height, gravity } = pile;
  for (const ball of balls) {
    if (ball.x < ball.r) ball.x = ball.r;
    else if (ball.x > width - ball.r) ball.x = width - ball.r;
    if (ball.y > height - ball.r) ball.y = height - ball.r;
    // The open top only holds balls in when gravity points at it.
    else if (ball.y < ball.r && gravity.y < 0) ball.y = ball.r;
  }
}

export function stepPile(pile: Pile, frameDt: number): void {
  const dt = frameDt / SUB_STEPS;
  if (dt <= 0) return;
  for (let sub = 0; sub < SUB_STEPS; sub += 1) {
    for (const ball of pile.balls) {
      ball.vx += pile.gravity.x * GRAVITY * dt;
      ball.vy += pile.gravity.y * GRAVITY * dt;
      ball.vx *= DRAG;
      ball.vy *= DRAG;
      // No ball may cross its own radius in one substep, or it tunnels through
      // the pile and the solver has to shove it back out.
      const reach = Math.hypot(ball.vx, ball.vy) * dt;
      const limit = ball.r * 0.8;
      if (reach > limit) {
        const scale = limit / reach;
        ball.vx *= scale;
        ball.vy *= scale;
      }
      ball.px = ball.x;
      ball.py = ball.y;
      ball.x += ball.vx * dt;
      ball.y += ball.vy * dt;
    }
    const { grid, cell } = buildGrid(pile);
    for (let pass = 0; pass < SOLVER_PASSES; pass += 1) {
      solveContacts(pile, grid, cell);
      solveWalls(pile);
    }
    for (const ball of pile.balls) {
      const travelX = ball.x - ball.px;
      const travel = Math.hypot(travelX, ball.y - ball.py);
      ball.vx = (ball.x - ball.px) / dt;
      ball.vy = (ball.y - ball.py) / dt;

      // The token rolls with its solved movement, including displacement from
      // neighbours. Free spin fades out once the pile comes to rest, so the
      // marks settle with the balls instead of hovering upright or shivering.
      ball.angularVelocity += (travelX / Math.max(ball.r, 1)) * 12;
      ball.angle += ball.angularVelocity * dt + travelX / Math.max(ball.r, 1);
      ball.facePhase += ball.faceVelocity * dt + (travel / Math.max(ball.r, 1)) * 0.18;
      const angularDrag = Math.pow(0.965, dt * 60);
      ball.angularVelocity *= angularDrag;
      ball.faceVelocity *= angularDrag;
    }
  }
}

/** Deepest overlap between any two balls, in pixels. */
export function worstOverlap(pile: Pile): number {
  let worst = 0;
  const { balls } = pile;
  for (let i = 0; i < balls.length; i += 1) {
    for (let j = i + 1; j < balls.length; j += 1) {
      const a = balls[i];
      const b = balls[j];
      const dist = Math.hypot(b.x - a.x, b.y - a.y);
      worst = Math.max(worst, a.r + b.r - dist);
    }
  }
  return worst;
}

/** How far the fastest ball is travelling, in pixels per second. */
export function fastestSpeed(pile: Pile): number {
  return pile.balls.reduce((top, ball) => Math.max(top, Math.hypot(ball.vx, ball.vy)), 0);
}
