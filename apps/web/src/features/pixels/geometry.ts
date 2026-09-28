import type { PixelPoint } from './protocol';

export type PixelView = { zoom: number; x: number; y: number };

// The same cover projection is used for drawing, hit testing and the app background.
export function pixelSide(width: number, height: number, zoom = 1): number {
  return Math.max(1, width, height) * zoom;
}

export function constrainPixelView(view: PixelView, width: number, height: number): PixelView {
  const side = pixelSide(width, height, view.zoom);
  const limitX = Math.max(0, (side - width) / 2);
  const limitY = Math.max(0, (side - height) / 2);
  return {
    ...view,
    x: Math.max(-limitX, Math.min(view.x, limitX)),
    y: Math.max(-limitY, Math.min(view.y, limitY)),
  };
}

export function pixelAt(
  point: PixelPoint,
  width: number,
  height: number,
  view: PixelView,
): PixelPoint | null {
  const side = pixelSide(width, height, view.zoom);
  const x = Math.floor(((point.x - (width - side) / 2 - view.x) / side) * 128);
  const y = Math.floor(((point.y - (height - side) / 2 - view.y) / side) * 128);
  return x < 0 || y < 0 || x > 127 || y > 127 ? null : { x, y };
}
