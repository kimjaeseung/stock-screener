import { useEffect, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Activity } from 'lucide-react';

interface Props {
  onComplete: () => void;
}

const LINES: { text: string; delay: number }[] = [
  { text: '> Initializing Signal Deck...', delay: 0 },
  { text: '> Connecting to KRX / NYSE / NASDAQ...', delay: 600 },
  { text: '> Scanning 2,500+ securities...', delay: 1300 },
  { text: '> Applying 6 technical analysis filters...', delay: 2100 },
  { text: '> Calculating Risk:Reward ratios...', delay: 2900 },
  { text: '', delay: 3500 },
  { text: '> ✅ Analysis complete. 10 signals detected.', delay: 3700 },
];

function TypedLine({ text, startDelay }: { text: string; startDelay: number }) {
  const [displayed, setDisplayed] = useState('');
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (!text) { setDone(true); return; }
    let i = 0;
    const timer = setTimeout(() => {
      const interval = setInterval(() => {
        i++;
        setDisplayed(text.slice(0, i));
        if (i >= text.length) { clearInterval(interval); setDone(true); }
      }, 22);
      return () => clearInterval(interval);
    }, startDelay);
    return () => clearTimeout(timer);
  }, [text, startDelay]);

  const isHighlight = text.includes('✅');
  const isMuted = text.startsWith('> Connecting') || text.startsWith('> Applying');

  return (
    <div className="min-h-5">
      <span
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: '0.85rem',
          color: isHighlight ? 'var(--accent-green)'
                : isMuted    ? 'rgba(0,255,204,0.5)'
                :              'rgba(0,255,204,0.85)',
          textShadow: isHighlight ? '0 0 12px rgba(0,210,106,0.6)' : 'none',
          fontWeight: isHighlight ? '700' : '400',
        }}
      >
        {displayed}
        {!done && <span className="cursor inline-block w-2 h-3.5 align-middle ml-0.5" style={{ background: 'var(--accent-cyan)' }} />}
      </span>
    </div>
  );
}

export default function IntroScreen({ onComplete }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rafRef = useRef(0);
  const [showButton, setShowButton] = useState(false);
  const [exiting, setExiting] = useState(false);

  // Canvas: floating candlestick-like lines
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d')!;
    const resize = () => { canvas.width = innerWidth; canvas.height = innerHeight; };
    resize();
    window.addEventListener('resize', resize);

    // Generate several chart "paths"
    const numLines = 5;
    type ChartLine = { pts: {x:number;y:number}[]; t: number; speed: number; color: string; alpha: number };
    const lines: ChartLine[] = Array.from({ length: numLines }, (_, i) => ({
      pts: Array.from({ length: 80 }, (_, j) => ({
        x: (j / 79) * innerWidth,
        y: innerHeight * (0.3 + i * 0.1) + Math.sin(j * 0.2 + i) * 60 + (Math.random() - 0.5) * 30,
      })),
      t: Math.random() * 100,
      speed: 0.003 + Math.random() * 0.004,
      color: ['#00d26a','#58a6ff','#f5a623','#00ffcc','#bc8cff'][i],
      alpha: 0.04 + i * 0.015,
    }));

    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      for (const line of lines) {
        line.t += line.speed;
        ctx.beginPath();
        ctx.strokeStyle = line.color;
        ctx.lineWidth = 1;
        ctx.globalAlpha = line.alpha;
        line.pts.forEach((p, j) => {
          const y = p.y + Math.sin(line.t + j * 0.15) * 25;
          j === 0 ? ctx.moveTo(p.x, y) : ctx.lineTo(p.x, y);
        });
        ctx.stroke();
        // fill under
        const last = line.pts[line.pts.length - 1];
        ctx.lineTo(last.x, canvas.height);
        ctx.lineTo(0, canvas.height);
        ctx.closePath();
        ctx.fillStyle = line.color;
        ctx.globalAlpha = line.alpha * 0.4;
        ctx.fill();
      }
      ctx.globalAlpha = 1;
      rafRef.current = requestAnimationFrame(draw);
    };
    draw();
    return () => { cancelAnimationFrame(rafRef.current); window.removeEventListener('resize', resize); };
  }, []);

  // Show button after all lines finish
  useEffect(() => {
    const last = LINES[LINES.length - 1];
    const timer = setTimeout(() => setShowButton(true), last.delay + last.text.length * 22 + 500);
    return () => clearTimeout(timer);
  }, []);

  const handleOpen = () => {
    setExiting(true);
    setTimeout(onComplete, 600);
  };

  return (
    <AnimatePresence>
      {!exiting ? (
        <motion.div
          key="intro"
          exit={{ y: '-100%', opacity: 0 }}
          transition={{ duration: 0.6, ease: [0.76, 0, 0.24, 1] }}
          className="fixed inset-0 z-50 flex items-center justify-center"
          style={{ background: 'var(--bg-primary)' }}
        >
          {/* Grid + radial glow */}
          <div className="absolute inset-0 bg-grid opacity-30 pointer-events-none" />
          <div className="absolute inset-0 pointer-events-none"
            style={{ background: 'radial-gradient(ellipse 60% 50% at 50% 50%, rgba(0,210,106,0.06) 0%, transparent 70%)' }} />

          <canvas ref={canvasRef} className="absolute inset-0 w-full h-full" />

          <div className="relative z-10 w-full max-w-xl px-6">
            {/* Logo */}
            <motion.div
              initial={{ opacity: 0, y: -16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5 }}
              className="flex items-center gap-3 mb-8"
            >
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{
                  background: 'linear-gradient(135deg, rgba(0,210,106,0.25), rgba(0,255,204,0.1))',
                  border: '1px solid rgba(0,210,106,0.4)',
                  boxShadow: '0 0 20px rgba(0,210,106,0.25)',
                }}
              >
                <Activity size={20} color="#00d26a" />
              </div>
              <div>
                <div
                  className="text-xl font-bold tracking-[0.2em]"
                  style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent-cyan)', textShadow: '0 0 12px rgba(0,255,204,0.4)' }}
                >
                  SIGNAL DECK
                </div>
                <div className="text-xs tracking-widest" style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                  TECHNICAL ANALYSIS SCREENER
                </div>
              </div>
            </motion.div>

            {/* Terminal window */}
            <motion.div
              initial={{ opacity: 0, scale: 0.97 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.4, delay: 0.15 }}
              className="rounded-2xl overflow-hidden"
              style={{
                background: 'rgba(10,12,18,0.92)',
                border: '1px solid rgba(0,210,106,0.2)',
                boxShadow: '0 0 40px rgba(0,210,106,0.08), 0 24px 48px rgba(0,0,0,0.5)',
              }}
            >
              {/* Title bar */}
              <div className="flex items-center gap-2 px-4 py-3"
                style={{ background: 'rgba(0,0,0,0.3)', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                <div className="flex gap-1.5">
                  <div className="w-3 h-3 rounded-full" style={{ background: '#ff5f57' }} />
                  <div className="w-3 h-3 rounded-full" style={{ background: '#febc2e' }} />
                  <div className="w-3 h-3 rounded-full" style={{ background: '#28c840' }} />
                </div>
                <span className="ml-2 text-xs" style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
                  signal-deck — screener v2.0
                </span>
              </div>

              {/* Content */}
              <div className="p-6 space-y-1.5">
                {LINES.map((line, i) =>
                  line.text === '' ? (
                    <div key={i} className="h-3" />
                  ) : (
                    <TypedLine key={i} text={line.text} startDelay={line.delay} />
                  )
                )}
              </div>
            </motion.div>

            {/* CTA */}
            <AnimatePresence>
              {showButton && (
                <motion.div
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.4 }}
                  className="mt-6 flex justify-center"
                >
                  <button
                    onClick={handleOpen}
                    className="relative group px-8 py-3.5 rounded-xl font-bold tracking-[0.15em] text-sm overflow-hidden"
                    style={{
                      fontFamily: 'var(--font-mono)',
                      background: 'transparent',
                      border: '1px solid rgba(0,210,106,0.6)',
                      color: 'var(--accent-green)',
                      cursor: 'pointer',
                    }}
                  >
                    {/* Animated bg on hover */}
                    <span
                      className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-300"
                      style={{ background: 'linear-gradient(135deg, rgba(0,210,106,0.15), rgba(0,255,204,0.05))' }}
                    />
                    {/* Pulse ring */}
                    <span
                      className="absolute inset-0 rounded-xl"
                      style={{
                        border: '1px solid rgba(0,210,106,0.4)',
                        animation: 'glow-pulse 2s ease-in-out infinite',
                      }}
                    />
                    <span className="relative z-10">OPEN DASHBOARD →</span>
                  </button>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
