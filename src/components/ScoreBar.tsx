import { motion } from 'framer-motion';

interface ScoreBarProps {
  label: string;
  score: number;
  max: number;
  delay?: number;
  color?: string;
}

export function ScoreBar({ label, score, max, delay = 0, color = 'var(--accent-green)' }: ScoreBarProps) {
  const pct = (score / max) * 100;
  const getColor = () => {
    if (pct >= 80) return '#00d26a';
    if (pct >= 60) return '#f5a623';
    return '#58a6ff';
  };
  const barColor = color === 'var(--accent-green)' ? getColor() : color;

  return (
    <div className="flex items-center gap-3">
      <span className="text-xs w-14 shrink-0" style={{ color: 'var(--text-secondary)' }}>{label}</span>
      <div className="flex-1 h-1.5 rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.06)' }}>
        <motion.div
          className="h-full rounded-full"
          style={{ background: barColor, boxShadow: `0 0 6px ${barColor}60` }}
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.8, delay, ease: 'easeOut' }}
        />
      </div>
      <span className="text-xs w-10 text-right shrink-0" style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
        {score}/{max}
      </span>
    </div>
  );
}

interface RiskRewardBarProps {
  riskPct: number;
  rewardPct: number;
  ratio: number;
  delay?: number;
}

export function RiskRewardBar({ riskPct, rewardPct, ratio, delay = 0 }: RiskRewardBarProps) {
  const totalAbs = Math.abs(riskPct) + rewardPct;
  const riskWidth = (Math.abs(riskPct) / totalAbs) * 50;
  const rewardWidth = (rewardPct / totalAbs) * 50;

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs" style={{ color: 'var(--accent-red)', fontFamily: 'var(--font-mono)' }}>
          손절 {riskPct.toFixed(1)}%
        </span>
        <span
          className="text-sm font-bold px-3 py-0.5 rounded-full"
          style={{
            fontFamily: 'var(--font-mono)',
            background: ratio >= 2 ? 'rgba(0,210,106,0.15)' : 'rgba(245,166,35,0.15)',
            color: ratio >= 2 ? 'var(--accent-green)' : 'var(--accent-gold)',
            border: `1px solid ${ratio >= 2 ? 'rgba(0,210,106,0.3)' : 'rgba(245,166,35,0.3)'}`,
          }}
        >
          R:R {ratio.toFixed(2)}
        </span>
        <span className="text-xs" style={{ color: 'var(--accent-green)', fontFamily: 'var(--font-mono)' }}>
          목표 +{rewardPct.toFixed(1)}%
        </span>
      </div>
      <div className="flex items-center gap-0.5 h-4">
        {/* Risk bar (left) */}
        <motion.div
          className="h-full rounded-l-full"
          style={{
            background: 'linear-gradient(to left, rgba(255,59,48,0.8), rgba(255,59,48,0.3))',
            width: 0,
          }}
          animate={{ width: `${riskWidth}%` }}
          transition={{ duration: 0.6, delay, ease: 'easeOut' }}
        />
        {/* Center line (entry) */}
        <div
          className="h-full w-0.5 shrink-0"
          style={{ background: 'rgba(255,255,255,0.6)' }}
        />
        {/* Reward bar (right) */}
        <motion.div
          className="h-full rounded-r-full"
          style={{
            background: 'linear-gradient(to right, rgba(0,210,106,0.8), rgba(0,210,106,0.3))',
            width: 0,
          }}
          animate={{ width: `${rewardWidth}%` }}
          transition={{ duration: 0.6, delay: delay + 0.1, ease: 'easeOut' }}
        />
      </div>
      <div className="flex justify-center mt-1">
        <span className="text-xs" style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>진입가 기준</span>
      </div>
    </div>
  );
}
