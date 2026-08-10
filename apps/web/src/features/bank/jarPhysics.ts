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
const FLIGHT_GRAVITY = 1120;
const FLIGHT_DRAG = 0.997;
const EDGE_RESTITUTION = 0.58;
const FLIGHT_CONTACT_PASSES = 3;
const WALL_CLEARANCE = 0.6;

// The visible neck is narrower than the body. These values are relative to
// the old chamber width and line up with the dark opening in empty-jar.webp.
// A token has to fit completely between them before the ceiling lets it pass:
// nothing can leak through a glass shoulder and pretend it used the neck.
export const MOUTH_LEFT = 0.18;
export const MOUTH_RIGHT = 0.82;
export const BOTTOM_CORNER_RATIO = 0.15;

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
  /** A short powered lift ends as soon as this token clears the real neck. */
  ejecting?: boolean;
}

/** Where the cursor is, in canvas pixels, while it is over the jar. */
export interface Pointer {
  x: number;
  y: number;
  radius: number;
}

export interface Pile {
  balls: Ball[];
  width: number;
  height: number;
  gravity: { x: number; y: number };
  /** Null whenever the cursor is away; the balls then simply settle again. */
  pointer: Pointer | null;
  mouth: { left: number; right: number };
}

export function createPile(width: number, height: number): Pile {
  return {
    balls: [],
    width,
    height,
    gravity: { x: 0, y: 1 },
    pointer: null,
    mouth: { left: width * MOUTH_LEFT, right: width * MOUTH_RIGHT },
  };
}

export function resizePile(pile: Pile, width: number, height: number): void {
  pile.width = width;
  pile.height = height;
  pile.mouth.left = width * MOUTH_LEFT;
  pile.mouth.right = width * MOUTH_RIGHT;
}

/** How wide a hole the cursor carves, relative to the jar. */
export function pointerRadius(width: number): number {
  return Math.max(width, 120) * 0.15;
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
  detachedCount = 0,
): void {
  const target = targetCount(pile, fillPercent);
  let poured = 0;
  while (pile.balls.length + detachedCount < target && poured < perFrame) {
    // GRAMчики belong to one physical set. A controlled tolerance keeps the pile
    // organic without turning it into unrelated large and small bubbles.
    const r = nominalRadius(pile.width) * (0.88 + random() * 0.24);
    const openingWidth = Math.max(0, pile.mouth.right - pile.mouth.left - r * 2);
    const x = pile.mouth.left + r + random() * openingWidth;
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
  if (pile.balls.length + detachedCount > target) {
    pile.balls.length = Math.max(0, target - detachedCount);
  }
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

/**
 * The cursor as a solid disc the balls cannot enter.
 *
 * Resolved by moving them, like every other contact here, which is why no force
 * needed tuning: velocity is read back from the distance actually travelled, so
 * a ball shoved aside carries exactly the speed the shove gave it and settles
 * back on its own once the cursor leaves.
 */
function solvePointer(pile: Pile): void {
  const pointer = pile.pointer;
  if (!pointer) return;
  for (const ball of pile.balls) {
    const dx = ball.x - pointer.x;
    const dy = ball.y - pointer.y;
    const min = pointer.radius + ball.r;
    const sq = dx * dx + dy * dy;
    if (sq >= min * min) continue;
    if (sq === 0) {
      // Dead centre has no direction to leave by; up is the way out of a pile.
      ball.y -= Math.min(min, ball.r);
      continue;
    }
    const dist = Math.sqrt(sq);
    // A fast sweep would otherwise teleport a ball clear across the jar and the
    // derived velocity would launch it. Move it at most its own radius a step.
    const push = Math.min(min - dist, ball.r);
    ball.x += (dx / dist) * push;
    ball.y += (dy / dist) * push;
  }
}

function solveWalls(pile: Pile): void {
  const { balls, width, height, mouth } = pile;
  for (const ball of balls) {
    const insideEdge = ball.r + WALL_CLEARANCE;
    if (ball.x < insideEdge) ball.x = insideEdge;
    else if (ball.x > width - insideEdge) ball.x = width - insideEdge;
    if (ball.y > height - insideEdge) ball.y = height - insideEdge;
    const fitsThroughMouth =
      ball.x - ball.r >= mouth.left + WALL_CLEARANCE &&
      ball.x + ball.r <= mouth.right - WALL_CLEARANCE;
    // The glass shoulder is a ceiling. Only the actual central mouth is open,
    // in both directions: new tokens fall in there and an energetic token can
    // leave there. Previously the whole body width was silently open.
    if (ball.y < insideEdge && !fitsThroughMouth) ball.y = insideEdge;

    // The image is a rounded glass vessel, not a rectangular box. Erode each
    // lower corner by the token radius so no part of a token can peek through
    // the curved outline by a few pixels.
    const cornerRadius = Math.min(width * BOTTOM_CORNER_RATIO, height * 0.18);
    const cornerY = height - cornerRadius;
    const effectiveRadius = Math.max(0, cornerRadius - insideEdge);
    const cornerX = ball.x < width / 2 ? cornerRadius : width - cornerRadius;
    if (
      effectiveRadius > 0 &&
      ball.y > cornerY &&
      (ball.x < cornerRadius || ball.x > width - cornerRadius)
    ) {
      const dx = ball.x - cornerX;
      const dy = ball.y - cornerY;
      const distance = Math.hypot(dx, dy);
      if (distance > effectiveRadius) {
        const scale = effectiveRadius / Math.max(distance, 0.0001);
        ball.x = cornerX + dx * scale;
        ball.y = cornerY + dy * scale;
      }
    }
  }
}

export interface FlyingBall extends Ball {
  flightAge: number;
}

export interface FlightField {
  balls: FlyingBall[];
  width: number;
  height: number;
  /** Opening coordinates in the full canvas coordinate system. */
  mouthLeft: number;
  mouthRight: number;
  mouthY: number;
  /** Body edges at the shoulder line, used as a solid roof. */
  jarLeft: number;
  jarRight: number;
  jarBottom: number;
}

export function createFlightField(
  width: number,
  height: number,
  jarLeft: number,
  mouthY: number,
  chamberWidth: number,
  chamberHeight = height - mouthY,
): FlightField {
  return {
    balls: [],
    width,
    height,
    jarLeft,
    jarRight: jarLeft + chamberWidth,
    jarBottom: mouthY + chamberHeight,
    mouthLeft: jarLeft + chamberWidth * MOUTH_LEFT,
    mouthRight: jarLeft + chamberWidth * MOUTH_RIGHT,
    mouthY,
  };
}

export function resizeFlightField(
  field: FlightField,
  width: number,
  height: number,
  jarLeft: number,
  mouthY: number,
  chamberWidth: number,
  chamberHeight = height - mouthY,
): void {
  field.width = width;
  field.height = height;
  field.jarLeft = jarLeft;
  field.jarRight = jarLeft + chamberWidth;
  field.jarBottom = mouthY + chamberHeight;
  field.mouthLeft = jarLeft + chamberWidth * MOUTH_LEFT;
  field.mouthRight = jarLeft + chamberWidth * MOUTH_RIGHT;
  field.mouthY = mouthY;
}

function clampFlyingBallToScreen(ball: FlyingBall, field: FlightField): void {
  if (ball.x < ball.r) {
    ball.x = ball.r;
    ball.vx = Math.abs(ball.vx) * EDGE_RESTITUTION;
  } else if (ball.x > field.width - ball.r) {
    ball.x = field.width - ball.r;
    ball.vx = -Math.abs(ball.vx) * EDGE_RESTITUTION;
  }
  if (ball.y < ball.r) {
    ball.y = ball.r;
    ball.vy = Math.abs(ball.vy) * EDGE_RESTITUTION;
  } else if (ball.y > field.height - ball.r) {
    ball.y = field.height - ball.r;
    ball.vy = -Math.abs(ball.vy) * 0.32;
    ball.vx *= 0.88;
  }
}

/** Keeps an exterior token outside the complete glass body, not only its roof. */
function solveJarExterior(ball: FlyingBall, field: FlightField): void {
  const left = field.jarLeft - ball.r - WALL_CLEARANCE;
  const right = field.jarRight + ball.r + WALL_CLEARANCE;
  const top = field.mouthY - ball.r - WALL_CLEARANCE;
  const bottom = field.jarBottom + ball.r + WALL_CLEARANCE;
  if (ball.x <= left || ball.x >= right || ball.y <= top || ball.y >= bottom) return;

  let edge: 'left' | 'right' | 'top' | 'bottom';
  if (ball.px <= left) edge = 'left';
  else if (ball.px >= right) edge = 'right';
  else if (ball.py <= top) edge = 'top';
  else if (ball.py >= bottom) edge = 'bottom';
  else {
    const distances = [
      ['left', ball.x - left],
      ['right', right - ball.x],
      ['top', ball.y - top],
      ['bottom', bottom - ball.y],
    ] as const;
    edge = distances.reduce((nearest, candidate) =>
      candidate[1] < nearest[1] ? candidate : nearest,
    )[0];
  }

  if (edge === 'left') {
    ball.x = left;
    ball.vx = -Math.abs(ball.vx) * EDGE_RESTITUTION;
  } else if (edge === 'right') {
    ball.x = right;
    ball.vx = Math.abs(ball.vx) * EDGE_RESTITUTION;
  } else if (edge === 'top') {
    ball.y = top;
    ball.vy = -Math.abs(ball.vy) * EDGE_RESTITUTION;
    const direction = ball.x < (field.jarLeft + field.jarRight) / 2 ? -1 : 1;
    ball.vx += direction * 34;
  } else {
    ball.y = bottom;
    ball.vy = Math.abs(ball.vy) * EDGE_RESTITUTION;
  }
}

/** Resolves exterior token contacts with equal-mass impulses and positional separation. */
function solveFlyingContacts(field: FlightField): void {
  const { balls } = field;
  for (let pass = 0; pass < FLIGHT_CONTACT_PASSES; pass += 1) {
    const cell = Math.max(1, ...balls.map((ball) => ball.r * 2));
    const grid: Grid = new Map();
    balls.forEach((ball, index) => {
      const key = cellKey(Math.floor(ball.x / cell), Math.floor(ball.y / cell));
      const bucket = grid.get(key);
      if (bucket) bucket.push(index);
      else grid.set(key, [index]);
    });

    for (let i = 0; i < balls.length; i += 1) {
      const a = balls[i];
      const cx = Math.floor(a.x / cell);
      const cy = Math.floor(a.y / cell);
      for (let gx = cx - 1; gx <= cx + 1; gx += 1) {
        for (let gy = cy - 1; gy <= cy + 1; gy += 1) {
          for (const j of grid.get(cellKey(gx, gy)) ?? []) {
            if (j <= i) continue;
            const b = balls[j];
            const dx = b.x - a.x;
            const dy = b.y - a.y;
            const minimum = a.r + b.r;
            const squared = dx * dx + dy * dy;
            if (squared >= minimum * minimum) continue;

            const distance = Math.sqrt(squared);
            const nx = distance > 0.0001 ? dx / distance : i % 2 === 0 ? 1 : -1;
            const ny = distance > 0.0001 ? dy / distance : 0;
            const correction = (minimum - distance) / 2 + 0.01;
            a.x -= nx * correction;
            a.y -= ny * correction;
            b.x += nx * correction;
            b.y += ny * correction;

            const relativeNormal = (b.vx - a.vx) * nx + (b.vy - a.vy) * ny;
            if (relativeNormal < 0) {
              const impulse = (-(1 + EDGE_RESTITUTION) * relativeNormal) / 2;
              a.vx -= impulse * nx;
              a.vy -= impulse * ny;
              b.vx += impulse * nx;
              b.vy += impulse * ny;
            }
          }
        }
      }
    }
    for (const ball of balls) {
      clampFlyingBallToScreen(ball, field);
      solveJarExterior(ball, field);
    }
  }
}

/**
 * Moves tokens that cleared the mouth from chamber coordinates into the full
 * stage. Their position and velocity are preserved, so crossing the lip is a
 * continuous motion rather than a second decorative animation.
 */
export function releaseEscaped(
  pile: Pile,
  field: FlightField,
  chamberLeft: number,
  chamberTop: number,
): number {
  let released = 0;
  for (let index = pile.balls.length - 1; index >= 0; index -= 1) {
    const ball = pile.balls[index];
    if (ball.y + ball.r > 0) continue;
    pile.balls.splice(index, 1);
    const wasEjecting = ball.ejecting;
    ball.ejecting = false;
    // The quiet idle lift receives a sideways roll as it clears the lip, so it
    // actually enters the surrounding screen instead of tracing the same
    // vertical line straight back into the jar. A gravity-driven spill keeps
    // its own physical velocity.
    const offsetFromCentre = ball.x - pile.width / 2;
    const launchDirection =
      Math.abs(offsetFromCentre) > ball.r * 0.25
        ? Math.sign(offsetFromCentre)
        : Math.sin(ball.angle + ball.facePhase) >= 0
          ? 1
          : -1;
    const launchVelocity = wasEjecting ? launchDirection * Math.max(150, pile.width * 1.1) : 0;
    field.balls.push({
      ...ball,
      x: ball.x + chamberLeft,
      px: ball.px + chamberLeft,
      y: ball.y + chamberTop,
      py: ball.py + chamberTop,
      vx: ball.vx + launchVelocity,
      flightAge: 0,
    });
    released += 1;
  }
  return released;
}

/**
 * Gives the highest token under the mouth just enough energy to clear it.
 * Used for the jar's very occasional idle breath and deterministic visual QA;
 * normal pointer/device-tilt motion can reach the same state on its own.
 */
export function liftSurfaceToken(pile: Pile, random: () => number = Math.random): boolean {
  if (pile.balls.some((ball) => ball.ejecting)) return false;
  const candidates = pile.balls.filter(
    (ball) => ball.x - ball.r >= pile.mouth.left && ball.x + ball.r <= pile.mouth.right,
  );
  if (!candidates.length) return false;
  const centre = pile.width / 2;
  const ball = candidates.reduce((best, candidate) => {
    const score = candidate.y + Math.abs(candidate.x - centre) * 0.08;
    const bestScore = best.y + Math.abs(best.x - centre) * 0.08;
    return score < bestScore ? candidate : best;
  });
  ball.ejecting = true;
  ball.vy = -Math.max(260, pile.height * 1.05);
  ball.vx = (random() - 0.5) * nominalRadius(pile.width) * 0.8;
  ball.angularVelocity += (random() - 0.5) * 7;
  return true;
}

/**
 * Advances the balls outside the jar and returns any that fell back through
 * the neck. Every substep clamps a full radius inside the stage, so neither a
 * fast impulse nor a resized viewport can lose a token beyond the screen.
 */
export function stepFlyingBalls(
  field: FlightField,
  pile: Pile,
  chamberLeft: number,
  chamberTop: number,
  gravity: { x: number; y: number },
  frameDt: number,
): number {
  if (frameDt <= 0 || !field.width || !field.height) return 0;
  const dt = Math.min(frameDt, 1 / 30) / SUB_STEPS;
  let returned = 0;

  for (let substep = 0; substep < SUB_STEPS; substep += 1) {
    for (let index = field.balls.length - 1; index >= 0; index -= 1) {
      const ball = field.balls[index];
      ball.flightAge += dt;
      ball.vx = (ball.vx + gravity.x * FLIGHT_GRAVITY * dt) * FLIGHT_DRAG;
      ball.vy = (ball.vy + gravity.y * FLIGHT_GRAVITY * dt) * FLIGHT_DRAG;
      // A token cannot travel far enough in one substep to jump through another
      // token or from one side of the glass body to the other.
      const reach = Math.hypot(ball.vx, ball.vy) * dt;
      const limit = ball.r * 0.65;
      if (reach > limit) {
        const scale = limit / reach;
        ball.vx *= scale;
        ball.vy *= scale;
      }
      ball.px = ball.x;
      ball.py = ball.y;
      ball.x += ball.vx * dt;
      ball.y += ball.vy * dt;

      clampFlyingBallToScreen(ball, field);

      const crossedShoulderDown =
        ball.vy > 0 && ball.py + ball.r <= field.mouthY && ball.y + ball.r > field.mouthY;
      if (crossedShoulderDown) {
        const fitsMouth =
          ball.x - ball.r >= field.mouthLeft + WALL_CLEARANCE &&
          ball.x + ball.r <= field.mouthRight - WALL_CLEARANCE;
        if (fitsMouth) {
          const localX = ball.x - chamberLeft;
          const localY = ball.y - chamberTop;
          const openingOccupied = pile.balls.some(
            (inside) =>
              Math.hypot(inside.x - localX, inside.y - localY) < (inside.r + ball.r) * 0.98,
          );
          if (!openingOccupied) {
            field.balls.splice(index, 1);
            pile.balls.push({
              ...ball,
              x: localX,
              px: ball.px - chamberLeft,
              y: localY,
              py: ball.py - chamberTop,
            });
            returned += 1;
            continue;
          }
          // Do not insert one body into another. The visible collision at the
          // lip buys the pile time to clear the opening naturally.
          ball.y = field.mouthY - ball.r;
          ball.vy = -Math.max(70, Math.abs(ball.vy) * 0.42);
          ball.vx += ball.x < (field.mouthLeft + field.mouthRight) / 2 ? -28 : 28;
          continue;
        }
        const touchesJar = ball.x + ball.r > field.jarLeft && ball.x - ball.r < field.jarRight;
        if (touchesJar) {
          ball.y = field.mouthY - ball.r;
          ball.vy = -Math.abs(ball.vy) * EDGE_RESTITUTION;
          // The curved shoulder sends a missed token away from the neck,
          // instead of letting it jitter on an invisible horizontal line.
          const direction = ball.x < (field.jarLeft + field.jarRight) / 2 ? -1 : 1;
          ball.vx += direction * 34;
        }
      }

      const travelX = ball.x - ball.px;
      const travel = Math.hypot(travelX, ball.y - ball.py);
      ball.angularVelocity += (travelX / Math.max(ball.r, 1)) * 7;
      ball.angle += ball.angularVelocity * dt + travelX / Math.max(ball.r, 1);
      ball.facePhase += ball.faceVelocity * dt + (travel / Math.max(ball.r, 1)) * 0.18;
      const angularDrag = Math.pow(0.97, dt * 60);
      ball.angularVelocity *= angularDrag;
      ball.faceVelocity *= angularDrag;
    }
    solveFlyingContacts(field);
  }
  return returned;
}

export function stepPile(pile: Pile, frameDt: number): void {
  const dt = frameDt / SUB_STEPS;
  if (dt <= 0) return;
  for (let sub = 0; sub < SUB_STEPS; sub += 1) {
    for (const ball of pile.balls) {
      if (ball.ejecting) {
        // A brief, quiet lift carries the selected surface token through the
        // empty headroom. It remains one continuously simulated body; only the
        // acceleration changes at the lip, where regular flight takes over.
        ball.vx *= 0.98;
        ball.vy = -Math.max(260, pile.height * 1.05);
      } else {
        ball.vx += pile.gravity.x * GRAVITY * dt;
        ball.vy += pile.gravity.y * GRAVITY * dt;
      }
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
      solvePointer(pile);
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
