import { useEffect, useRef } from 'react';
import { motion } from 'framer-motion';

interface Props {
  score: number;
  size?: number;
  delay?: number;
}

export default function CircularScore({ score, size = 72, delay = 0 }: Props) {
  const countRef = useRef<HTMLSpanElement>(null);

  const radius = (size - 8) / 2;
  const circumference = 2 * Math.PI * radius;
  const pct = Math.min(score, 100) / 100;
  const dashOffset = circumference * (1 - pct);

  const color =
    score >= 80 ? '#00d26a' :
    score >= 65 ? '#f5a623' :
    score >= 50 ? '#58a6ff' :
                  '#8b949e';

  // count-up animation
  useEffect(() => {
    if (!countRef.current) return;
    const duration = 1000;
    const startTime = performance.now() + delay * 1000;

    const tick = (now: number) => {
      if (now < startTime) { requestAnimationFrame(tick); return; }
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      const current = Math.round(eased * score);
      if (countRef.current) countRef.current.textContent = String(current);
      if (progress < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }, [score, delay]);

  return (
    <div className="relative flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
        {/* Track */}
        <circle
          cx={size / 2} cy={size / 2} r={radius}
          fill="none"
          stroke="rgba(255,255,255,0.06)"
          strokeWidth={5}
        />
        {/* Arc */}
        <motion.circle
          cx={size / 2} cy={size / 2} r={radius}
          fill="none"
          stroke={color}
          strokeWidth={5}
          strokeLinecap="round"
          strokeDasharray={circumference}
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset: dashOffset }}
          transition={{ duration: 1, delay, ease: 'easeOut' }}
          style={{ filter: `drop-shadow(0 0 4px ${color}80)` }}
        />
      </svg>
      {/* Center text */}
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span
          ref={countRef}
          className="font-bold leading-none"
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: size * 0.27,
            color,
            textShadow: `0 0 8px ${color}60`,
          }}
        >
          0
        </span>
        <span style={{ fontSize: size * 0.14, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
          /100
        </span>
      </div>
    </div>
  );
}
