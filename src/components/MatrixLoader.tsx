import { useEffect, useRef } from 'react';

export default function MatrixLoader() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d')!;

    const resize = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    };
    resize();
    window.addEventListener('resize', resize);

    const fontSize = 13;
    const cols = Math.floor(canvas.width / fontSize);
    const drops: number[] = Array(cols).fill(1);

    const chars = '01234567890ABCDEF▲▼+-%.MACD RSI ATR ADX SMA EMA BB KR US '.split('');

    let frame = 0;
    const draw = () => {
      ctx.fillStyle = 'rgba(10,10,15,0.08)';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.font = `${fontSize}px "JetBrains Mono", monospace`;

      for (let i = 0; i < drops.length; i++) {
        const char = chars[Math.floor(Math.random() * chars.length)];
        const brightness = Math.random();
        if (brightness > 0.95) {
          ctx.fillStyle = '#00ffcc';
        } else if (brightness > 0.85) {
          ctx.fillStyle = 'rgba(0,210,106,0.9)';
        } else {
          ctx.fillStyle = `rgba(0,210,106,${0.15 + brightness * 0.3})`;
        }
        ctx.fillText(char, i * fontSize, drops[i] * fontSize);

        if (drops[i] * fontSize > canvas.height && Math.random() > 0.975) {
          drops[i] = 0;
        }
        drops[i]++;
      }
      frame = requestAnimationFrame(draw);
    };
    draw();

    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener('resize', resize);
    };
  }, []);

  return (
    <div className="fixed inset-0 z-50 flex flex-col items-center justify-center"
      style={{ background: 'var(--bg-primary)' }}>
      <canvas ref={canvasRef} className="absolute inset-0 w-full h-full opacity-40" />
      <div className="relative z-10 text-center">
        <div
          className="text-2xl font-bold mb-4 tracking-widest"
          style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent-cyan)', textShadow: '0 0 20px rgba(0,255,204,0.5)' }}
        >
          SIGNAL DECK
        </div>
        <div className="text-sm" style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent-green)' }}>
          데이터 로딩 중...
        </div>
        <div className="flex items-center justify-center gap-1 mt-4">
          {[0,1,2].map(i => (
            <div
              key={i}
              className="w-1.5 h-1.5 rounded-full"
              style={{
                background: 'var(--accent-green)',
                animation: `blink 1s ${i * 0.3}s infinite`,
              }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
