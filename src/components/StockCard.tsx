import { useState } from 'react';
import { motion } from 'framer-motion';
import { ChevronRight, TrendingUp, TrendingDown } from 'lucide-react';
import type { StockResult } from '../data/types';
import SparkLine from './SparkLine';
import CircularScore from './CircularScore';
import { ScoreBar } from './ScoreBar';

// ─── Rank styling ──────────────────────────────────────────────────────────────
const RANK_CONFIG = [
  { medal: '🥇', label: 'TOP PICK', glow: 'rgba(245,166,35,0.2)',  border: 'rgba(245,166,35,0.5)',  badge: '#f5a623' },
  { medal: '🥈', label: '2ND',      glow: 'rgba(168,168,168,0.15)', border: 'rgba(168,168,168,0.4)', badge: '#a8a8a8' },
  { medal: '🥉', label: '3RD',      glow: 'rgba(205,127,50,0.15)',  border: 'rgba(205,127,50,0.4)',  badge: '#cd7f32' },
];

const SCORE_BARS = [
  { key: 'trend' as const,        label: '추세',    max: 25 },
  { key: 'golden_cross' as const, label: '크로스',  max: 20 },
  { key: 'momentum' as const,     label: '모멘텀', max: 20 },
  { key: 'volume' as const,       label: '거래량', max: 20 },
  { key: 'support' as const,      label: '지지',    max: 10 },
  { key: 'bollinger' as const,    label: '볼린저', max: 10 },
];

const CHECKLIST_ITEMS = [
  { key: 'above_ma200' as const,         label: '200일선↑' },
  { key: 'golden_cross_recent' as const, label: '골든크로스' },
  { key: 'volume_surge' as const,        label: '거래량급증' },
  { key: 'rsi_healthy' as const,         label: 'RSI적정' },
  { key: 'macd_bullish' as const,        label: 'MACD강세' },
  { key: 'trend_strong' as const,        label: '추세강함' },
  { key: 'rr_ratio_good' as const,       label: '손익비2:1+' },
];

interface Props {
  stock: StockResult;
  index: number;
  onSelect: (s: StockResult) => void;
  isKr: boolean;
}

export default function StockCard({ stock, index, onSelect, isKr }: Props) {
  const [hovered, setHovered] = useState(false);

  const up     = stock.change_pct >= 0;
  const rankCfg = RANK_CONFIG[index] ?? null;
  const currency = isKr ? '₩' : '$';
  const priceStr = isKr
    ? Math.round(stock.price).toLocaleString('ko-KR')
    : Number(stock.price).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  const borderColor = rankCfg
    ? (hovered ? rankCfg.border : 'rgba(255,255,255,0.08)')
    : (hovered ? 'rgba(255,255,255,0.15)' : 'rgba(255,255,255,0.06)');
  const glowColor   = rankCfg ? rankCfg.glow : (up ? 'rgba(0,210,106,0.08)' : 'rgba(255,59,48,0.06)');

  return (
    <motion.div
      layoutId={`card-${stock.ticker}`}
      initial={{ opacity: 0, y: 28 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: index * 0.07 }}
      onHoverStart={() => setHovered(true)}
      onHoverEnd={() => setHovered(false)}
      onClick={() => onSelect(stock)}
      className="rounded-2xl p-5 cursor-pointer overflow-hidden relative"
      style={{
        background: 'rgba(13,17,23,0.7)',
        backdropFilter: 'blur(12px)',
        border: `1px solid ${borderColor}`,
        boxShadow: hovered
          ? `0 0 30px ${glowColor}, 0 12px 40px rgba(0,0,0,0.3)`
          : `0 0 0px transparent`,
        transform: hovered ? 'translateY(-4px)' : 'none',
        transition: 'transform 0.2s ease, box-shadow 0.25s ease, border-color 0.2s ease',
      }}
    >
      {/* TOP PICK badge for ranks 1-3 */}
      {rankCfg && (
        <div
          className="absolute top-0 right-0 px-3 py-1 rounded-bl-xl rounded-tr-2xl text-xs font-bold tracking-widest"
          style={{
            fontFamily: 'var(--font-mono)',
            background: `${rankCfg.badge}22`,
            color: rankCfg.badge,
            border: `1px solid ${rankCfg.badge}44`,
          }}
        >
          {rankCfg.label}
        </div>
      )}

      {/* Header: medal + name + score gauge */}
      <div className="flex items-start gap-3 mb-4">
        <motion.span
          className="text-2xl shrink-0 mt-0.5"
          animate={{ scale: hovered ? 1.2 : 1 }}
          transition={{ type: 'spring', stiffness: 400 }}
        >
          {index < 3 ? rankCfg!.medal : `#${stock.rank}`}
        </motion.span>

        <div className="flex-1 min-w-0">
          <div className="font-bold text-base truncate" style={{ color: 'var(--text-primary)' }}>
            {stock.name}
          </div>
          <div className="flex items-center flex-wrap gap-1.5 mt-1">
            <span className="text-xs" style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
              {stock.ticker}
            </span>
            <span style={{ color: 'var(--text-muted)' }}>·</span>
            <span
              className="text-xs px-1.5 py-0.5 rounded"
              style={{ background: 'rgba(88,166,255,0.1)', color: 'var(--accent-blue)', border: '1px solid rgba(88,166,255,0.2)' }}
            >
              {stock.market}
            </span>
            <span style={{ color: 'var(--text-muted)' }}>·</span>
            <span className="text-xs truncate" style={{ color: 'var(--text-muted)' }}>{stock.sector}</span>
          </div>
        </div>

        {/* Circular score */}
        <CircularScore score={stock.score} size={68} delay={index * 0.07} />
      </div>

      {/* Price + sparkline */}
      <div className="flex items-end justify-between mb-4">
        <div>
          <div
            className="text-xl font-bold"
            style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}
          >
            {currency}{priceStr}
          </div>
          <div className="flex items-center gap-1 mt-0.5">
            {up ? <TrendingUp size={13} color="#00d26a" /> : <TrendingDown size={13} color="#ff3b30" />}
            <span
              className="text-sm font-bold"
              style={{ fontFamily: 'var(--font-mono)', color: up ? 'var(--accent-green)' : 'var(--accent-red)' }}
            >
              {up ? '+' : ''}{stock.change_pct.toFixed(1)}%
            </span>
          </div>
        </div>
        <SparkLine data={stock.price_history_30d} width={150} height={48} />
      </div>

      {/* Score breakdown bars */}
      <div
        className="space-y-1.5 mb-4 p-3 rounded-xl"
        style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.04)' }}
      >
        <div className="text-xs font-semibold mb-2 tracking-wider" style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
          SCORE BREAKDOWN
        </div>
        {SCORE_BARS.map((bar, i) => (
          <ScoreBar
            key={bar.key}
            label={bar.label}
            score={stock.score_breakdown[bar.key]}
            max={bar.max}
            delay={index * 0.06 + i * 0.06}
          />
        ))}
      </div>

      {/* Risk/Reward visual slider */}
      <RRSlider rr={stock.risk_reward} isKr={isKr} delay={index * 0.06} />

      {/* Signals */}
      {stock.signals.length > 0 && (
        <div className="space-y-1 mb-4">
          {stock.signals.slice(0, 3).map((sig, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: index * 0.06 + i * 0.08 + 0.4 }}
              className="text-xs flex items-start gap-2"
              style={{ color: 'var(--text-secondary)' }}
            >
              <span className="shrink-0 mt-0.5" style={{ color: 'var(--accent-green)' }}>▸</span>
              {sig}
            </motion.div>
          ))}
        </div>
      )}

      {/* Checklist chips */}
      <div className="flex flex-wrap gap-1.5 mb-4">
        {CHECKLIST_ITEMS.map((item, i) => {
          const checked = stock.checklist[item.key];
          return (
            <motion.span
              key={item.key}
              initial={{ opacity: 0, scale: 0.85 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: index * 0.06 + i * 0.06 + 0.35 }}
              className="text-xs px-2 py-0.5 rounded-full"
              style={{
                background: checked ? 'rgba(0,210,106,0.1)' : 'rgba(255,255,255,0.03)',
                color: checked ? 'var(--accent-green)' : 'var(--text-muted)',
                border: `1px solid ${checked ? 'rgba(0,210,106,0.25)' : 'rgba(255,255,255,0.05)'}`,
              }}
            >
              {checked ? '✅' : '·'} {item.label}
            </motion.span>
          );
        })}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between pt-3" style={{ borderTop: '1px solid rgba(255,255,255,0.05)' }}>
        <div className="flex gap-3 text-xs" style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
          <span>RSI <span style={{ color: 'var(--text-secondary)' }}>{stock.technicals.rsi_14.toFixed(0)}</span></span>
          <span>ADX <span style={{ color: 'var(--text-secondary)' }}>{stock.technicals.adx.toFixed(0)}</span></span>
          <span>Vol <span style={{ color: 'var(--text-secondary)' }}>{stock.technicals.volume_ratio.toFixed(1)}</span>×</span>
        </div>
        <motion.div className="flex items-center gap-1 text-xs" style={{ color: 'var(--accent-cyan)' }} whileHover={{ x: 3 }}>
          상세보기 <ChevronRight size={13} />
        </motion.div>
      </div>
    </motion.div>
  );
}

// ─── Risk/Reward Slider ────────────────────────────────────────────────────────
interface RRSliderProps {
  rr: StockResult['risk_reward'];
  isKr: boolean;
  delay: number;
}

function RRSlider({ rr, isKr, delay }: RRSliderProps) {
  const currency = isKr ? '₩' : '$';
  const fmt = (n: number) =>
    isKr ? Math.round(n).toLocaleString('ko-KR') : n.toFixed(2);

  const riskAbs  = Math.abs(rr.risk_pct);
  const total    = riskAbs + rr.reward_pct;
  const riskW    = (riskAbs / total) * 100;
  const rewardW  = (rr.reward_pct / total) * 100;
  const entryPct = riskW; // entry marker sits at end of risk zone

  const rrColor = rr.ratio >= 2 ? '#00d26a' : '#f5a623';

  return (
    <div
      className="mb-4 p-3 rounded-xl"
      style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.04)' }}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs" style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>손익비 (R:R)</span>
        <span
          className="text-sm font-bold px-2.5 py-0.5 rounded-full"
          style={{
            fontFamily: 'var(--font-mono)',
            background: `${rrColor}18`,
            color: rrColor,
            border: `1px solid ${rrColor}40`,
          }}
        >
          {rr.ratio.toFixed(2)} : 1
        </span>
      </div>

      {/* Slider track */}
      <div className="relative h-6 rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.04)' }}>
        {/* Risk zone */}
        <motion.div
          className="absolute left-0 top-0 h-full"
          style={{ background: 'linear-gradient(90deg, rgba(255,59,48,0.6), rgba(255,59,48,0.3))', width: 0 }}
          animate={{ width: `${riskW}%` }}
          transition={{ duration: 0.7, delay, ease: 'easeOut' }}
        />
        {/* Reward zone */}
        <motion.div
          className="absolute top-0 h-full"
          style={{
            background: 'linear-gradient(90deg, rgba(0,210,106,0.3), rgba(0,210,106,0.6))',
            left: `${entryPct}%`,
            width: 0,
          }}
          animate={{ width: `${rewardW}%` }}
          transition={{ duration: 0.7, delay: delay + 0.1, ease: 'easeOut' }}
        />
        {/* Entry marker */}
        <div
          className="absolute top-0 h-full w-0.5"
          style={{
            left: `${entryPct}%`,
            background: 'rgba(255,255,255,0.8)',
            boxShadow: '0 0 6px rgba(255,255,255,0.6)',
            animation: 'glow-pulse 2s ease-in-out infinite',
          }}
        />
      </div>

      {/* Labels */}
      <div className="flex justify-between mt-1.5 text-xs" style={{ fontFamily: 'var(--font-mono)' }}>
        <span style={{ color: 'var(--accent-red)' }}>
          {currency}{fmt(rr.stop_loss)}<br />
          <span style={{ color: 'rgba(255,59,48,0.6)' }}>{rr.risk_pct.toFixed(1)}%</span>
        </span>
        <span className="text-center" style={{ color: 'var(--text-muted)' }}>
          진입<br />
          {currency}{fmt(rr.entry)}
        </span>
        <span className="text-right" style={{ color: 'var(--accent-green)' }}>
          {currency}{fmt(rr.take_profit)}<br />
          <span style={{ color: 'rgba(0,210,106,0.6)' }}>+{rr.reward_pct.toFixed(1)}%</span>
        </span>
      </div>
    </div>
  );
}
