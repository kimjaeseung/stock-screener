import { useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, TrendingUp, TrendingDown } from 'lucide-react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  BarChart, Bar, ReferenceLine, RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
} from 'recharts';
import type { StockResult } from '../data/types';

interface Props {
  stock: StockResult | null;
  onClose: () => void;
  isKr: boolean;
}

function GaugeWidget({ label, value, min, max, goodMin, goodMax, unit = '' }: {
  label: string; value: number; min: number; max: number;
  goodMin: number; goodMax: number; unit?: string;
}) {
  const pct = Math.min(Math.max((value - min) / (max - min), 0), 1) * 100;
  const inGood = value >= goodMin && value <= goodMax;
  const color = inGood ? '#00d26a' : value > goodMax ? '#ff3b30' : '#f5a623';
  return (
    <div className="p-3 rounded-xl" style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid var(--border-subtle)' }}>
      <div className="flex justify-between items-center mb-2">
        <span className="text-xs" style={{ color: 'var(--text-muted)' }}>{label}</span>
        <span className="text-sm font-bold" style={{ fontFamily: 'var(--font-mono)', color }}>
          {value.toFixed(1)}{unit}
        </span>
      </div>
      <div className="h-1.5 rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.08)' }}>
        <motion.div
          className="h-full rounded-full"
          style={{ background: color, width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.8, ease: 'easeOut' }}
        />
      </div>
      <div className="flex justify-between mt-1">
        <span className="text-xs" style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>{min}</span>
        <span className="text-xs" style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>{max}</span>
      </div>
    </div>
  );
}

export default function StockDetail({ stock, onClose, isKr }: Props) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose]);

  if (!stock) return null;

  const currency = isKr ? '₩' : '$';
  const up = stock.change_pct >= 0;

  // Chart data
  const chartData = stock.price_history_30d.map((price, i) => ({
    day: i + 1,
    price,
    ma20: i >= 19 ? stock.ma_20 * (0.95 + (i - 19) * 0.003) : null,
    ma60: stock.ma_60 * (0.98 + i * 0.001),
  }));

  const volumeData = stock.price_history_30d.map((_, i) => ({
    day: i + 1,
    vol: Math.random() * 0.8 + 0.6,
    up: stock.price_history_30d[i] >= (stock.price_history_30d[i - 1] ?? 0),
  }));

  const radarData = [
    { subject: '추세', value: (stock.score_breakdown.trend / 25) * 100 },
    { subject: '크로스', value: (stock.score_breakdown.golden_cross / 20) * 100 },
    { subject: '모멘텀', value: (stock.score_breakdown.momentum / 20) * 100 },
    { subject: '거래량', value: (stock.score_breakdown.volume / 15) * 100 },
    { subject: '지지', value: (stock.score_breakdown.support / 10) * 100 },
    { subject: '볼린저', value: (stock.score_breakdown.bollinger / 10) * 100 },
  ];

  const priceMin = Math.min(...stock.price_history_30d) * 0.99;
  const priceMax = Math.max(...stock.price_history_30d) * 1.01;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 flex items-center justify-center p-4"
        style={{ backdropFilter: 'blur(20px)', background: 'rgba(10,10,15,0.85)' }}
        onClick={e => e.target === e.currentTarget && onClose()}
      >
        <motion.div
          layoutId={`card-${stock.ticker}`}
          className="w-full max-w-5xl max-h-[90vh] overflow-y-auto rounded-2xl"
          style={{
            background: 'rgba(16,20,28,0.98)',
            border: '1px solid rgba(255,255,255,0.1)',
            boxShadow: '0 25px 80px rgba(0,0,0,0.6)',
          }}
        >
          {/* Modal Header */}
          <div className="sticky top-0 z-10 flex items-center justify-between p-5 pb-4"
            style={{ background: 'rgba(16,20,28,0.98)', borderBottom: '1px solid var(--border-subtle)' }}>
            <div className="flex items-center gap-3">
              <div>
                <div className="font-bold text-xl" style={{ color: 'var(--text-primary)' }}>{stock.name}</div>
                <div className="text-xs flex items-center gap-2 mt-0.5">
                  <span style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>{stock.ticker}</span>
                  <span style={{ color: 'var(--text-muted)' }}>·</span>
                  <span style={{ color: 'var(--accent-blue)' }}>{stock.market}</span>
                  <span style={{ color: 'var(--text-muted)' }}>·</span>
                  <span style={{ color: 'var(--text-muted)' }}>{stock.sector}</span>
                </div>
              </div>
              <div className="ml-4 text-right">
                <div className="text-2xl font-bold" style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>
                  {currency}{isKr ? stock.price.toLocaleString('ko-KR') : stock.price.toFixed(2)}
                </div>
                <div className="flex items-center gap-1 justify-end">
                  {up ? <TrendingUp size={13} color="#00d26a" /> : <TrendingDown size={13} color="#ff3b30" />}
                  <span style={{ fontFamily: 'var(--font-mono)', color: up ? 'var(--accent-green)' : 'var(--accent-red)' }}>
                    {up ? '+' : ''}{stock.change_pct.toFixed(1)}%
                  </span>
                </div>
              </div>
            </div>
            <button
              onClick={onClose}
              className="w-8 h-8 rounded-full flex items-center justify-center transition-colors"
              style={{ background: 'rgba(255,255,255,0.06)', border: '1px solid var(--border-subtle)' }}
            >
              <X size={16} color="var(--text-secondary)" />
            </button>
          </div>

          <div className="p-5 space-y-5">
            {/* Price Chart */}
            <div className="rounded-xl p-4" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-subtle)' }}>
              <div className="text-xs font-semibold mb-3 tracking-wider" style={{ color: 'var(--text-muted)' }}>
                가격 차트 (30일) + 이동평균선
              </div>
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={chartData} margin={{ top: 5, right: 10, bottom: 5, left: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
                  <XAxis dataKey="day" tick={{ fontSize: 10, fill: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }} />
                  <YAxis domain={[priceMin, priceMax]} tick={{ fontSize: 10, fill: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }} width={50} />
                  <Tooltip
                    contentStyle={{ background: 'rgba(16,20,28,0.95)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, fontSize: 12 }}
                    labelStyle={{ color: 'var(--text-muted)' }}
                  />
                  <ReferenceLine y={stock.risk_reward.stop_loss} stroke="#ff3b30" strokeDasharray="4 2" strokeOpacity={0.7} label={{ value: '손절', fill: '#ff3b30', fontSize: 10 }} />
                  <ReferenceLine y={stock.risk_reward.entry} stroke="rgba(255,255,255,0.5)" strokeDasharray="4 2" strokeOpacity={0.7} label={{ value: '진입', fill: 'rgba(255,255,255,0.5)', fontSize: 10 }} />
                  <ReferenceLine y={stock.risk_reward.take_profit} stroke="#00d26a" strokeDasharray="4 2" strokeOpacity={0.7} label={{ value: '목표', fill: '#00d26a', fontSize: 10 }} />
                  <Line type="monotone" dataKey="price" stroke="#58a6ff" strokeWidth={2} dot={false} name="가격" />
                  <Line type="monotone" dataKey="ma20" stroke="#f5a623" strokeWidth={1.5} dot={false} strokeOpacity={0.8} name="MA20" connectNulls />
                  <Line type="monotone" dataKey="ma60" stroke="#bc8cff" strokeWidth={1.5} dot={false} strokeOpacity={0.8} name="MA60" connectNulls />
                </LineChart>
              </ResponsiveContainer>

              {/* Volume chart */}
              <ResponsiveContainer width="100%" height={60}>
                <BarChart data={volumeData} margin={{ top: 2, right: 10, bottom: 0, left: 10 }}>
                  <Bar dataKey="vol" fill="#58a6ff" opacity={0.4} radius={[1, 1, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>

              {/* Legend */}
              <div className="flex flex-wrap gap-4 mt-2 text-xs" style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
                {[['가격', '#58a6ff'], ['MA20', '#f5a623'], ['MA60', '#bc8cff'], ['손절', '#ff3b30'], ['목표', '#00d26a']].map(([l, c]) => (
                  <span key={l} className="flex items-center gap-1">
                    <span className="w-3 h-0.5 inline-block rounded" style={{ background: c }} />
                    {l}
                  </span>
                ))}
              </div>
            </div>

            {/* Indicators + Radar */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Gauge indicators */}
              <div className="space-y-3">
                <div className="text-xs font-semibold tracking-wider" style={{ color: 'var(--text-muted)' }}>기술적 지표</div>
                <GaugeWidget label="RSI (14)" value={stock.technicals.rsi_14} min={0} max={100} goodMin={30} goodMax={70} />
                <GaugeWidget label="ADX (14)" value={stock.technicals.adx} min={0} max={60} goodMin={25} goodMax={50} />
                <GaugeWidget label="거래량 비율" value={stock.technicals.volume_ratio} min={0} max={5} goodMin={1.5} goodMax={4} unit="×" />
                <GaugeWidget label="볼린저 위치" value={stock.technicals.bb_position * 100} min={0} max={100} goodMin={20} goodMax={80} unit="%" />
              </div>

              {/* Radar chart */}
              <div className="rounded-xl p-4" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-subtle)' }}>
                <div className="text-xs font-semibold mb-2 tracking-wider" style={{ color: 'var(--text-muted)' }}>점수 레이더</div>
                <ResponsiveContainer width="100%" height={200}>
                  <RadarChart data={radarData}>
                    <PolarGrid stroke="rgba(255,255,255,0.08)" />
                    <PolarAngleAxis dataKey="subject" tick={{ fontSize: 11, fill: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }} />
                    <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
                    <Radar name="점수" dataKey="value" stroke="#00d26a" fill="#00d26a" fillOpacity={0.15} strokeWidth={1.5} />
                  </RadarChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Signals + Risk/Reward detail */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Signals */}
              <div className="rounded-xl p-4" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-subtle)' }}>
                <div className="text-xs font-semibold mb-3 tracking-wider" style={{ color: 'var(--text-muted)' }}>탐지된 시그널</div>
                <div className="space-y-2">
                  {stock.signals.map((sig, i) => (
                    <motion.div
                      key={i}
                      initial={{ opacity: 0, x: -10 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: i * 0.1 }}
                      className="flex items-center gap-2 text-sm"
                      style={{ color: 'var(--text-secondary)' }}
                    >
                      <span style={{ color: 'var(--accent-green)' }}>✓</span>
                      {sig}
                    </motion.div>
                  ))}
                </div>
              </div>

              {/* Risk/Reward details */}
              <div className="rounded-xl p-4" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-subtle)' }}>
                <div className="text-xs font-semibold mb-3 tracking-wider" style={{ color: 'var(--text-muted)' }}>손익비 상세</div>
                <div className="space-y-3">
                  {[
                    { label: '진입가', value: `${currency}${isKr ? stock.risk_reward.entry.toLocaleString('ko-KR') : stock.risk_reward.entry.toFixed(2)}`, color: 'var(--text-primary)' },
                    { label: '손절가', value: `${currency}${isKr ? stock.risk_reward.stop_loss.toLocaleString('ko-KR') : stock.risk_reward.stop_loss.toFixed(2)} (${stock.risk_reward.risk_pct.toFixed(1)}%)`, color: 'var(--accent-red)' },
                    { label: '목표가', value: `${currency}${isKr ? stock.risk_reward.take_profit.toLocaleString('ko-KR') : stock.risk_reward.take_profit.toFixed(2)} (+${stock.risk_reward.reward_pct.toFixed(1)}%)`, color: 'var(--accent-green)' },
                    { label: '손익비', value: `${stock.risk_reward.ratio.toFixed(2)} : 1`, color: stock.risk_reward.ratio >= 2 ? 'var(--accent-green)' : 'var(--accent-gold)' },
                  ].map(item => (
                    <div key={item.label} className="flex justify-between items-center">
                      <span className="text-xs" style={{ color: 'var(--text-muted)' }}>{item.label}</span>
                      <span className="text-sm font-bold" style={{ fontFamily: 'var(--font-mono)', color: item.color }}>
                        {item.value}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <p className="text-xs text-center" style={{ color: 'var(--text-muted)' }}>
              ⚠️ 본 분석은 기술적 지표 기반의 참고 자료이며, 투자 조언이 아닙니다. 투자의 책임은 본인에게 있습니다.
            </p>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
