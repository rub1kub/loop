import { useEffect, useRef } from 'react';

export function ProbabilityCanvas({ chance, status }: { chance: number; status: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const elapsed = useRef(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const context = canvas.getContext('2d');
    if (!context) return;

    function draw(time: number) {
      const ratio = window.devicePixelRatio || 1;
      const width = canvas?.clientWidth ?? 280;
      const height = canvas?.clientHeight ?? 280;
      if (!canvas || !context) return;
      canvas.width = width * ratio;
      canvas.height = height * ratio;
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      context.clearRect(0, 0, width, height);
      const centerX = width / 2;
      const centerY = height / 2;
      const radius = Math.min(width, height) * 0.34;
      context.lineWidth = 18;
      context.lineCap = 'round';
      context.strokeStyle = '#242424';
      context.beginPath();
      context.arc(centerX, centerY, radius, 0, Math.PI * 2);
      context.stroke();
      context.strokeStyle = '#f5f5f5';
      context.beginPath();
      context.arc(
        centerX,
        centerY,
        radius,
        -Math.PI / 2,
        -Math.PI / 2 + Math.PI * 2 * (chance / 100),
      );
      context.stroke();
      const angle = -Math.PI / 2 + (time / 1400) * Math.PI * 2;
      context.fillStyle = '#ffffff';
      context.beginPath();
      context.arc(
        centerX + Math.cos(angle) * radius,
        centerY + Math.sin(angle) * radius,
        status === 'idle' ? 3 : 6,
        0,
        Math.PI * 2,
      );
      context.fill();
      context.fillStyle = '#ffffff';
      context.textAlign = 'center';
      context.textBaseline = 'middle';
      context.font = '600 52px -apple-system, BlinkMacSystemFont, sans-serif';
      context.fillText(`${chance}%`, centerX, centerY - 3);
    }

    let frame = 0;
    function animate(time: number) {
      elapsed.current = time;
      draw(time);
      frame = requestAnimationFrame(animate);
    }
    frame = requestAnimationFrame(animate);
    window.advanceTime = (milliseconds) => {
      elapsed.current += milliseconds;
      draw(elapsed.current);
    };
    window.render_game_to_text = () =>
      JSON.stringify({
        coordinateSystem: 'origin top-left; x right; y down',
        mode: status,
        chancePercent: chance,
        opponentChancePercent: 100 - chance,
        visibleEntity: { type: 'probability-ring', x: 140, y: 140, radius: 95 },
      });
    return () => {
      cancelAnimationFrame(frame);
      delete window.advanceTime;
      delete window.render_game_to_text;
    };
  }, [chance, status]);

  return <canvas ref={canvasRef} className="probability-canvas" aria-label={`Шанс ${chance}%`} />;
}
