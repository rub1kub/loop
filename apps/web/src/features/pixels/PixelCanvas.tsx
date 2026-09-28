import { Crosshair, Minus, Plus } from '@phosphor-icons/react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { PixelPoint, PixelState } from './protocol';
import { constrainPixelView as constrain, pixelAt, pixelSide } from './geometry';

type View = { zoom: number; x: number; y: number };
const INITIAL_VIEW: View = { zoom: 1, x: 0, y: 0 };
const clamp = (value: number, min: number, max: number) => Math.max(min, Math.min(value, max));

export function PixelCanvas({
  state,
  background = false,
  selection,
  onSelect,
  focus,
}: {
  state: PixelState;
  background?: boolean;
  selection?: PixelPoint;
  onSelect?: (point: PixelPoint) => void;
  focus?: PixelPoint | null;
}) {
  const host = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [dimensions, setDimensions] = useState({ width: 1, height: 1 });
  const [view, setView] = useState(INITIAL_VIEW);
  const pointers = useRef(new Map<number, PixelPoint>());
  const gesture = useRef({
    moved: false,
    start: { x: 0, y: 0 },
    last: { x: 0, y: 0 },
    distance: 0,
  });

  const bitmap = useMemo(() => {
    if (!state.pixels || state.palette.length !== 16) return null;
    const image = document.createElement('canvas');
    image.width = image.height = 128;
    const context = image.getContext('2d');
    if (!context) return null;
    const data = context.createImageData(128, 128);
    const colors = state.palette.map((hex) => [
      parseInt(hex.slice(1, 3), 16),
      parseInt(hex.slice(3, 5), 16),
      parseInt(hex.slice(5, 7), 16),
    ]);
    for (let index = 0; index < state.pixels.length; index++) {
      const rgb = colors[parseInt(state.pixels[index], 16)] ?? colors[0];
      data.data.set([...rgb, 255], index * 4);
    }
    context.putImageData(data, 0, 0);
    return image;
  }, [state.pixels, state.palette]);

  useEffect(() => {
    const element = host.current;
    if (!element) return;
    const resize = () => {
      const { width, height } = element.getBoundingClientRect();
      setDimensions({ width: Math.max(1, width), height: Math.max(1, height) });
    };
    resize();
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(resize);
    observer?.observe(element);
    window.addEventListener('resize', resize);
    return () => {
      observer?.disconnect();
      window.removeEventListener('resize', resize);
    };
  }, []);

  const zoomAt = useCallback(
    (zoom: number | ((previous: number) => number), point?: PixelPoint) => {
      setView((stored) => {
        const previous = constrain(stored, dimensions.width, dimensions.height);
        const nextZoom = clamp(typeof zoom === 'function' ? zoom(previous.zoom) : zoom, 1, 16);
        const focal = point ?? { x: dimensions.width / 2, y: dimensions.height / 2 };
        const ratio = nextZoom / previous.zoom;
        return constrain(
          {
            zoom: nextZoom,
            x:
              focal.x -
              dimensions.width / 2 -
              (focal.x - dimensions.width / 2 - previous.x) * ratio,
            y:
              focal.y -
              dimensions.height / 2 -
              (focal.y - dimensions.height / 2 - previous.y) * ratio,
          },
          dimensions.width,
          dimensions.height,
        );
      });
    },
    [dimensions],
  );

  useEffect(() => {
    if (!focus || background || dimensions.width < 2) return;
    const side = pixelSide(dimensions.width, dimensions.height, 4);
    const frame = window.requestAnimationFrame(() =>
      setView(
        constrain(
          {
            zoom: 4,
            x: ((64 - focus.x - 0.5) * side) / 128,
            y: ((64 - focus.y - 0.5) * side) / 128,
          },
          dimensions.width,
          dimensions.height,
        ),
      ),
    );
    return () => window.cancelAnimationFrame(frame);
  }, [focus, background, dimensions]);

  useEffect(() => {
    const element = canvas.current;
    if (!element || !bitmap) return;
    const { width, height } = dimensions;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    element.width = Math.round(width * dpr);
    element.height = Math.round(height * dpr);
    const context = element.getContext('2d');
    if (!context) return;
    context.scale(dpr, dpr);
    context.imageSmoothingEnabled = false;
    context.fillStyle = '#080809';
    context.fillRect(0, 0, width, height);
    const visibleView = constrain(view, width, height);
    const side = pixelSide(width, height, background ? 1 : visibleView.zoom);
    const left = (width - side) / 2 + (background ? 0 : visibleView.x);
    const top = (height - side) / 2 + (background ? 0 : visibleView.y);
    context.drawImage(bitmap, left, top, side, side);
    if (background) return;
    const unit = side / 128;
    if (unit >= 12) {
      context.beginPath();
      for (let i = 1; i < 128; i++) {
        const x = left + unit * i,
          y = top + unit * i;
        if (x >= 0 && x <= width) {
          context.moveTo(x, Math.max(0, top));
          context.lineTo(x, Math.min(height, top + side));
        }
        if (y >= 0 && y <= height) {
          context.moveTo(Math.max(0, left), y);
          context.lineTo(Math.min(width, left + side), y);
        }
      }
      context.strokeStyle = 'rgba(255,255,255,0.12)';
      context.lineWidth = 1;
      context.stroke();
    }
    if (selection) {
      const x = left + selection.x * unit,
        y = top + selection.y * unit;
      context.lineWidth = 4;
      context.strokeStyle = '#000';
      context.strokeRect(x - 1, y - 1, unit + 2, unit + 2);
      context.lineWidth = 2;
      context.strokeStyle = '#fff';
      context.strokeRect(x - 1, y - 1, unit + 2, unit + 2);
      const cx = x + unit / 2,
        cy = y + unit / 2;
      context.beginPath();
      context.moveTo(cx - unit / 2 - 12, cy);
      context.lineTo(cx - unit / 2 - 5, cy);
      context.moveTo(cx + unit / 2 + 5, cy);
      context.lineTo(cx + unit / 2 + 12, cy);
      context.moveTo(cx, cy - unit / 2 - 12);
      context.lineTo(cx, cy - unit / 2 - 5);
      context.moveTo(cx, cy + unit / 2 + 5);
      context.lineTo(cx, cy + unit / 2 + 12);
      context.stroke();
    }
  }, [bitmap, dimensions, view, selection, background]);

  useEffect(() => {
    const element = canvas.current;
    if (!element || background) return;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      const rect = element.getBoundingClientRect();
      zoomAt((previous) => previous * (event.deltaY < 0 ? 1.25 : 0.8), {
        x: event.clientX - rect.left,
        y: event.clientY - rect.top,
      });
    };
    element.addEventListener('wheel', onWheel, { passive: false });
    return () => element.removeEventListener('wheel', onWheel);
  }, [background, zoomAt]);

  const localPoint = (event: { clientX: number; clientY: number }): PixelPoint => {
    const rect = canvas.current!.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  };

  return (
    <div ref={host} className={background ? 'pixel-background-canvas' : 'pixel-viewport'}>
      <canvas
        ref={canvas}
        data-testid={background ? 'pixel-background' : 'pixel-canvas'}
        data-zoom={background ? undefined : view.zoom.toFixed(3)}
        data-pan-x={
          background ? undefined : constrain(view, dimensions.width, dimensions.height).x.toFixed(2)
        }
        aria-hidden={background || undefined}
        tabIndex={background ? -1 : 0}
        aria-label={
          background ? undefined : 'Общее полотно. Выбери пиксель нажатием или стрелками клавиатуры'
        }
        onPointerDown={
          background
            ? undefined
            : (event) => {
                event.currentTarget.setPointerCapture(event.pointerId);
                const point = localPoint(event);
                pointers.current.set(event.pointerId, point);
                if (pointers.current.size === 1)
                  gesture.current = { moved: false, start: point, last: point, distance: 0 };
                if (pointers.current.size === 2) {
                  const [a, b] = [...pointers.current.values()];
                  gesture.current.moved = true;
                  gesture.current.distance = Math.hypot(a.x - b.x, a.y - b.y);
                }
              }
        }
        onPointerMove={
          background
            ? undefined
            : (event) => {
                if (!pointers.current.has(event.pointerId)) return;
                const point = localPoint(event);
                pointers.current.set(event.pointerId, point);
                if (pointers.current.size === 2) {
                  const [a, b] = [...pointers.current.values()];
                  const distance = Math.hypot(a.x - b.x, a.y - b.y);
                  if (gesture.current.distance > 0) {
                    const ratio = distance / gesture.current.distance;
                    zoomAt((previous) => previous * ratio, {
                      x: (a.x + b.x) / 2,
                      y: (a.y + b.y) / 2,
                    });
                  }
                  gesture.current.distance = distance;
                } else if (pointers.current.size === 1) {
                  if (
                    Math.hypot(
                      point.x - gesture.current.start.x,
                      point.y - gesture.current.start.y,
                    ) > 5
                  )
                    gesture.current.moved = true;
                  if (gesture.current.moved) {
                    const last = gesture.current.last;
                    setView((stored) => {
                      const previous = constrain(stored, dimensions.width, dimensions.height);
                      return constrain(
                        {
                          ...previous,
                          x: previous.x + point.x - last.x,
                          y: previous.y + point.y - last.y,
                        },
                        dimensions.width,
                        dimensions.height,
                      );
                    });
                  }
                }
                gesture.current.last = point;
              }
        }
        onPointerUp={
          background
            ? undefined
            : (event) => {
                const point = localPoint(event);
                if (pointers.current.size === 1 && !gesture.current.moved) {
                  const selected = pixelAt(
                    point,
                    dimensions.width,
                    dimensions.height,
                    constrain(view, dimensions.width, dimensions.height),
                  );
                  if (selected) {
                    onSelect?.(selected);
                    if (view.zoom < 4) zoomAt(4, point);
                  }
                }
                pointers.current.delete(event.pointerId);
                if (pointers.current.size === 1)
                  gesture.current.last = [...pointers.current.values()][0];
              }
        }
        onPointerCancel={() => {
          pointers.current.clear();
          gesture.current.moved = true;
        }}
        onKeyDown={
          background
            ? undefined
            : (event) => {
                const moves: Record<string, PixelPoint> = {
                  ArrowLeft: { x: -1, y: 0 },
                  ArrowRight: { x: 1, y: 0 },
                  ArrowUp: { x: 0, y: -1 },
                  ArrowDown: { x: 0, y: 1 },
                };
                const move = moves[event.key];
                if (!move || !selection) return;
                event.preventDefault();
                const point = {
                  x: clamp(selection.x + move.x, 0, 127),
                  y: clamp(selection.y + move.y, 0, 127),
                };
                onSelect?.(point);
                const side = pixelSide(dimensions.width, dimensions.height, view.zoom);
                setView((previous) =>
                  constrain(
                    {
                      ...previous,
                      x: ((64 - point.x - 0.5) * side) / 128,
                      y: ((64 - point.y - 0.5) * side) / 128,
                    },
                    dimensions.width,
                    dimensions.height,
                  ),
                );
              }
        }
      />
      {!background && (
        <div className="pixel-zoom-controls">
          <button
            aria-label="Приблизить полотно"
            onClick={() => zoomAt(view.zoom * 2)}
            disabled={view.zoom >= 16}
          >
            <Plus size={18} />
          </button>
          <button
            aria-label="Отдалить полотно"
            onClick={() => zoomAt(view.zoom / 2)}
            disabled={view.zoom <= 1}
          >
            <Minus size={18} />
          </button>
          <button aria-label="В центр полотна" onClick={() => setView(INITIAL_VIEW)}>
            <Crosshair size={18} />
          </button>
        </div>
      )}
    </div>
  );
}
