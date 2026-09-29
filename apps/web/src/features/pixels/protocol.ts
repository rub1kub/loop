import { z } from 'zod';

export const pixelRoundSchema = z.object({
  id: z.string(),
  starts_at: z.string(),
  ends_at: z.string(),
  revision: z.number().int().nonnegative(),
  archived: z.boolean(),
});
export const pixelChangeSchema = z.object({
  revision: z.number().int().nonnegative(),
  index: z.number().int().min(0).max(16383),
  color: z.number().int().min(0).max(15),
});
export const pixelStateSchema = z.object({
  enabled: z.boolean(),
  round: pixelRoundSchema.nullable(),
  server_time: z.string(),
  ready_at: z.string().nullable(),
  size: z.literal(128),
  cooldown_seconds: z.number().int().positive(),
  palette: z.array(z.string().regex(/^#[0-9a-f]{6}$/i)).max(16),
  pixels: z
    .string()
    .length(16384)
    .regex(/^[0-9a-f]+$/)
    .nullable(),
  changes: z.array(pixelChangeSchema).max(512),
});
export const pixelReceiptSchema = pixelChangeSchema.extend({
  round_id: z.string(),
  server_time: z.string(),
  ready_at: z.string(),
  replayed: z.boolean(),
});
const pixelTeamSchema = z.object({
  team_id: z.string(),
  name: z.string(),
  held_pixels: z.number(),
  points: z.number(),
  is_mine: z.boolean(),
});
export const pixelScoresSchema = z.object({
  teams: z.array(pixelTeamSchema),
  my_team: pixelTeamSchema.nullable(),
});
export const pixelShareSchema = z.object({
  url: z.url(),
  image_url: z.url(),
  prepared_message_id: z.string().nullable(),
});
export const pixelModerationSchema = z.array(
  z.object({
    id: z.string(),
    reason: z.string(),
    x: z.number(),
    y: z.number(),
    width: z.number(),
    height: z.number(),
    created_at: z.string(),
  }),
);
export type PixelState = z.infer<typeof pixelStateSchema>;
export type PixelRound = z.infer<typeof pixelRoundSchema>;
export type PixelReceipt = z.infer<typeof pixelReceiptSchema>;
export type PixelScores = z.infer<typeof pixelScoresSchema>;
export type PixelModeration = z.infer<typeof pixelModerationSchema>;
export type PixelPoint = { x: number; y: number };
export type PixelPlace = PixelPoint & { round_id: string; operation_id: string; color: number };

export function decodePixels(encoded: string): Uint8Array {
  return Uint8Array.from(encoded, (color) => parseInt(color, 16));
}

/** Reject holes and old responses instead of drawing a partly applied board. */
export function mergePixelState(previous: PixelState | null, incoming: PixelState): PixelState {
  if (!incoming.enabled || !incoming.round) return incoming;
  if (!previous?.round || previous.round.id !== incoming.round.id) {
    if (!incoming.pixels) throw new Error('Нужен свежий снимок полотна');
    if (previous?.round && previous.round.id > incoming.round.id) return previous;
    return incoming;
  }
  const newerClock = Date.parse(incoming.server_time) >= Date.parse(previous.server_time);
  const timing = newerClock
    ? { server_time: incoming.server_time, ready_at: incoming.ready_at }
    : { server_time: previous.server_time, ready_at: previous.ready_at };
  if (incoming.round.revision < previous.round.revision) return { ...previous, ...timing };
  if (incoming.pixels) return { ...incoming, ...timing };
  const pixels = (previous.pixels ?? '').split('');
  let revision = previous.round.revision;
  for (const change of incoming.changes) {
    if (change.revision <= revision) continue;
    if (change.revision !== revision + 1) throw new Error('Нужен свежий снимок полотна');
    pixels[change.index] = change.color.toString(16);
    revision = change.revision;
  }
  if (revision !== incoming.round.revision || pixels.length !== 16384) {
    throw new Error('Нужен свежий снимок полотна');
  }
  return { ...incoming, ...timing, pixels: pixels.join(''), changes: [] };
}
