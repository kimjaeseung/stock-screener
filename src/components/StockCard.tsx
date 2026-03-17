import { useState } from 'react';
import { motion } from 'framer-motion';
import { ChevronRight, TrendingUp, TrendingDown } from 'lucide-react';
import type { StockResult } from '../data/types';
import SparkLine from './SparkLine';
import CircularScore from './CircularScore';

// ─── Rank config ───────────────────────────────────────────────────────────────
const RANK_CONFIG = [
  { medal: '🥇', label: 'TOP PICK', accent: '#f5a623' },
  { medal: '🥈', label: '2ND',      accent: '#a8a8a8' },
  { medal: '🥉', label: '3RD',      accent: '#cd7f32' },
];

// Score breakdown config — ordered for display
const SCORE_BARS = [
  { key: 'trend'        as const, label: '추세',   max: 25, color: '#58a6ff' },
  { key: 'golden_cross' as const, label: '크로스', max: 20, color: '#f5a623' },
  { key: 'momentum'     as const, label: '모멘텀', max: 20, color: '#00d26a' },
  { key: 'volume'       as const, label: '거래량', max: 20, color: '#00ffcc' },
  { key: 'support'      as const, label: '지지',   max: 10, color: '#a78bfa' },
  { key: 'bollinger'    as const, label: '볼린저', max: 10, color: '#fb923c' },
];

interface Props {
  stock: StockResult;
  index: number;
  onSelect: (s: StockResult) => void;
  isKr: boolean;
}

export default function StockCard({ stock, index, onSelect, isKr }: Props) {
  const [hovered, setHovered] = useState(false);

  const up       = stock.change_pct >= 0;
  const rankCfg  = RANK_CONFIG[index] ?? null;
  const currency = isKr ? '₩' : '$';
  const priceStr = isKr
    ? Math.round(stock.price).toLocaleString('ko-KR')
    : Number(stock.price).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  const accent = rankCfg ? rankCfg.accent : (up ? 'var(--accent-green)' : 'rgba(255,255,255,0.15)');
  const borderColor = hovered
    ? (rankCfg ? `${rankCfg.accent}60` : 'rgba(255,255,255,0.2)')
    : (rankCfg ? `${rankCfg.accent}28` : 'rgba(255,255,255,0.07)');
  const glowShadow = hovered
    ? (rankCfg
        ? `0 0 32px ${rankCfg.accent}28, 0 16px 48px rgba(0,0,0,0.4)`
        : `0 0 24px rgba(0,210,106,0.1), 0 16px 48px rgba(0,0,0,0.4)`)
    : '0 4px 20px rgba(0,0,0,0.2)';

  return (
    <motion.div
      layoutId={`card-${stock.ticker}`}
      initial={{ opacity: 0, y: 24 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: index * 0.06 }}
      onHoverStart={() => setHovered(true)}
      onHoverEnd={() => setHovered(false)}
      onClick={() => onSelect(stock)}
      className="rounded-2xl cursor-pointer overflow-hidden"
      style={{
        background: 'linear-gradient(145deg, rgba(16,22,32,0.95), rgba(10,14,22,0.98))',
        border: `1px solid ${borderColor}`,
        boxShadow: glowShadow,
        transform: hovered ? 'translateY(-3px)' : 'none',
        transition: 'transform 0.2s ease, box-shadow 0.25s ease, border-color 0.25s ease',
      }}
    >
      {/* Top accent bar */}
      {rankCfg && (
        <div style={{ height: 2, background: `linear-gradient(90deg, transparent, ${rankCfg.accent}, transparent)` }} />
      )}

      <div className="p-5">
        {/* ── Header: rank + name + score ── */}
        <div className="flex items-start gap-3 mb-4">
          <div className="flex flex-col items-center gap-1 shrink-0 mt-0.5">
            <span className="text-2xl leading-none">
              {index < 3 ? rankCfg!.medal : `#${stock.rank}`}
            </span>
            {rankCfg && (
              <span
                className="text-xs font-bold tracking-widest px-1.5 py-0.5 rounded"
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: '0.6rem',
                  background: `${rankCfg.accent}18`,
                  color: rankCfg.accent,
                }}
              >
                {rankCfg.label}
              </span>
            )}
          </div>

          <div className="flex-1 min-w-0">
            <div className="font-bold text-base leading-tight truncate" style={{ color: 'var(--text-primary)' }}>
              {stock.name}
            </div>
            <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
              <span
                className="text-xs font-semibold"
                style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}
              >
                {stock.ticker}
              </span>
              <span style={{ color: 'var(--border-subtle)' }}>·</span>
              <span
                className="text-xs px-1.5 py-0.5 rounded-md font-medium"
                style={{
                  background: 'rgba(88,166,255,0.1)',
                  color: 'var(--accent-blue)',
                  border: '1px solid rgba(88,166,255,0.2)',
                }}
              >
                {stock.market}
              </span>
              <span style={{ color: 'var(--border-subtle)' }}>·</span>
              <span className="text-xs truncate" style={{ color: 'var(--text-muted)' }}>{stock.sector}</span>
            </div>
          </div>

          <CircularScore score={stock.score} size={68} delay={index * 0.06} />
        </div>

        {/* ── Price row ── */}
        <div className="flex items-end justify-between mb-4">
          <div>
            <div
              className="text-2xl font-bold tracking-tight"
              style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}
            >
              {currency}{priceStr}
            </div>
            <div className="flex items-center gap-1.5 mt-1">
              {up ? <TrendingUp size={13} color="#00d26a" /> : <TrendingDown size={13} color="#ff3b30" />}
              <span
                className="text-sm font-bold"
                style={{
                  fontFamily: 'var(--font-mono)',
                  color: up ? 'var(--accent-green)' : 'var(--accent-red)',
                }}
              >
                {up ? '+' : ''}{stock.change_pct.toFixed(2)}%
              </span>
            </div>
          </div>
          <SparkLine data={stock.price_history_30d} width={140} height={44} />
        </div>

        {/* ── Score breakdown ── */}
        <div
          className="rounded-xl p-3.5 mb-3.5"
          style={{
            background: 'rgba(255,255,255,0.025)',
            border: '1px solid rgba(255,255,255,0.05)',
          }}
        >
          <div
            className="text-xs font-semibold mb-3 tracking-widest"
            style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}
          >
            SCORE BREAKDOWN
          </div>
          <div className="space-y-2">
            {SCORE_BARS.map((bar, i) => {
              const score = stock.score_breakdown[bar.key];
              const pct = (score / bar.max) * 100;
              return (
                <motion.div
                  key={bar.key}
                  className="flex items-center gap-2.5"
                  initial={{ opacity: 0, x: -6 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: index * 0.05 + i * 0.05 + 0.1 }}
                >
                  <span
                    className="shrink-0 text-xs"
                    style={{
                      width: 38,
                      color: 'var(--text-secondary)',
                      fontFamily: 'var(--font-mono)',
                      fontSize: '0.7rem',
                    }}
                  >
                    {bar.label}
                  </span>
                  <div
                    className="flex-1 rounded-full overflow-hidden"
                    style={{ height: 6, background: 'rgba(255,255,255,0.06)' }}
                  >
                    <motion.div
                      className="h-full rounded-full"
                      style={{
                        background: pct >= 70
                          ? bar.color
                          : pct >= 40
                            ? `${bar.color}cc`
                            : `${bar.color}55`,
                        boxShadow: pct >= 70 ? `0 0 8px ${bar.color}60` : 'none',
                      }}
                      initial={{ width: 0 }}
                      animate={{ width: `${pct}%` }}
                      transition={{ duration: 0.9, delay: index * 0.05 + i * 0.05 + 0.15, ease: 'easeOut' }}
                    />
                  </div>
                  <span
                    className="shrink-0 text-right"
                    style={{
                      width: 32,
                      fontFamily: 'var(--font-mono)',
                      fontSize: '0.68rem',
                      color: pct >= 70 ? bar.color : 'var(--text-muted)',
                    }}
                  >
                    {score}/{bar.max}
                  </span>
                </motion.div>
              );
            })}
          </div>
        </div>

        {/* ── Signals ── */}
        {stock.signals.length > 0 && (
          <div className="space-y-1.5 mb-3.5">
            {stock.signals.slice(0, 3).map((sig, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, x: -6 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: index * 0.05 + i * 0.07 + 0.35 }}
                className="flex items-start gap-2 text-xs"
                style={{ color: 'var(--text-secondary)', lineHeight: 1.5 }}
              >
                <span className="shrink-0 mt-0.5" style={{ color: accent }}>▸</span>
                <span>{sig}</span>
              </motion.div>
            ))}
          </div>
        )}

        {/* ── Footer: key metrics + detail CTA ── */}
        <div
          className="flex items-center justify-between pt-3"
          style={{ borderTop: '1px solid rgba(255,255,255,0.05)' }}
        >
          <div
            className="flex gap-4 text-xs"
            style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}
          >
            <span>
              RSI{' '}
              <span style={{ color: 'var(--text-secondary)' }}>
                {stock.technicals.rsi_14.toFixed(0)}
              </span>
            </span>
            <span>
              ADX{' '}
              <span style={{ color: 'var(--text-secondary)' }}>
                {stock.technicals.adx.toFixed(0)}
              </span>
            </span>
            <span>
              Vol{' '}
              <span
                style={{
                  color: stock.technicals.volume_ratio >= 2
                    ? 'var(--accent-green)'
                    : stock.technicals.volume_ratio >= 1.2
                      ? 'var(--accent-cyan)'
                      : 'var(--text-secondary)',
                }}
              >
                {stock.technicals.volume_ratio.toFixed(1)}×
              </span>
            </span>
            <span>
              R:R{' '}
              <span
                style={{
                  color: stock.risk_reward.ratio >= 2
                    ? 'var(--accent-green)'
                    : 'var(--accent-gold, #f5a623)',
                }}
              >
                {stock.risk_reward.ratio.toFixed(1)}:1
              </span>
            </span>
          </div>
          <motion.div
            className="flex items-center gap-1 text-xs font-medium"
            style={{ color: 'var(--accent-cyan)' }}
            whileHover={{ x: 3 }}
          >
            상세보기 <ChevronRight size={12} />
          </motion.div>
        </div>
      </div>
    </motion.div>
  );
}
