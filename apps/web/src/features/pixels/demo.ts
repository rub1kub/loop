import type { PixelPlace, PixelReceipt, PixelState } from './protocol';

const cooldownSeconds = 2;
const palette = [
  '#101012',
  '#ffffff',
  '#919198',
  '#45454d',
  '#ef4444',
  '#ff8c42',
  '#f5cb5c',
  '#a3d977',
  '#35b779',
  '#50c8c6',
  '#63b5ed',
  '#4775d1',
  '#8062c5',
  '#c77acb',
  '#ee9ca7',
  '#a07855',
];
let timeOffset = 0;
const pixels = new Uint8Array(128 * 128);
// Only a local review fixture. Production always starts with the actual server board.
const stamp = (x: number, y: number, color: number, pattern: string[], scale = 1) => {
  pattern.forEach((row, dy) =>
    [...row].forEach((v, dx) => {
      if (v !== '#') return;
      for (let sy = 0; sy < scale; sy++)
        for (let sx = 0; sx < scale; sx++) {
          pixels[(y + dy * scale + sy) * 128 + x + dx * scale + sx] = color;
        }
    }),
  );
};
stamp(13, 19, 14, ['.##.##.', '#######', '#######', '.#####.', '..###..', '...#...'], 3);
stamp(
  82,
  15,
  10,
  ['..#####..', '.#######.', '##.#.#.##', '#########', '#########', '#.#.#.#.#'],
  3,
);
stamp(16, 82, 6, ['...#...', '.#####.', '.#####.', '#######', '.#####.', '.#####.', '...#...'], 3);
stamp(84, 84, 8, ['#....#', '##..##', '######', '.####.', '..##..', '..##..'], 3);
stamp(
  48,
  53,
  1,
  [
    '##......##',
    '###....###',
    '.###..###.',
    '..######..',
    '...####...',
    '...####...',
    '..######..',
    '.###..###.',
    '###....###',
    '##......##',
  ],
  3,
);
let revision = 64;
let readyAt = 0;
const receipts = new Map<string, PixelReceipt>();
const clock = () => Date.now() + timeOffset;
const initialTime = clock();
const round = {
  id: '2099-01-05',
  starts_at: new Date(initialTime - 86400000).toISOString(),
  ends_at: new Date(initialTime + 5 * 86400000).toISOString(),
  archived: false,
};

export function demoPixelState(): PixelState {
  return {
    enabled: true,
    round: { ...round, revision },
    server_time: new Date(clock()).toISOString(),
    ready_at: readyAt ? new Date(readyAt).toISOString() : null,
    size: 128,
    cooldown_seconds: cooldownSeconds,
    palette,
    pixels: [...pixels].map((c) => c.toString(16)).join(''),
    changes: [],
  };
}

export function demoPlace(body: PixelPlace): PixelReceipt {
  const previous = receipts.get(body.operation_id);
  if (previous) return { ...previous, replayed: true };
  if (clock() < readyAt) throw new Error('Следующий пиксель ещё не готов');
  const index = body.y * 128 + body.x;
  if (pixels[index] === body.color) throw new Error('Здесь уже этот цвет');
  pixels[index] = body.color;
  revision++;
  readyAt = clock() + cooldownSeconds * 1000;
  const result = {
    revision,
    index,
    color: body.color,
    round_id: round.id,
    server_time: new Date(clock()).toISOString(),
    ready_at: new Date(readyAt).toISOString(),
    replayed: false,
  };
  receipts.set(body.operation_id, result);
  return result;
}

export function advanceDemoPixels(ms: number): void {
  timeOffset += ms;
}
