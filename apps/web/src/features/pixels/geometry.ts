import type { PixelPoint } from './protocol';

export type PixelView = { zoom: number; x: number; y: number };
export function pixelAt(
  point: PixelPoint,
  width: number,
  height: number,
  view: PixelView,
): PixelPoint | null {
  const side = Math.min(width - 24, height - 24) * view.zoom;
  const x = Math.floor(((point.x - (width - side) / 2 - view.x) / side) * 128);
  const y = Math.floor(((point.y - (height - side) / 2 - view.y) / side) * 128);
  return x < 0 || y < 0 || x > 127 || y > 127 ? null : { x, y };
}
