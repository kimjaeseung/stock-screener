import { motion } from 'framer-motion';
import { TrendingUp, TrendingDown, Activity, Film } from 'lucide-react';
import type { MarketSummary } from '../data/types';

interface Props {
  marketSummary: MarketSummary;
  updatedAt: string;
}

function MarketCard({ label, index, changePct }: { label: string; index: number; changePct: number }) {
  const up = changePct >= 0;
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      className="glass rounded-xl px-4 py-2 flex items-center gap-3"
      style={{
        border: `1px solid ${up ? 'rgba(0,210,106,0.25)' : 'rgba(255,59,48,0.25)'}`,
        boxShadow: up ? 'var(--glow-green)' : 'var(--glow-red)',
        minWidth: 130,
      }}
    >
      <div>
        <div className="text-xs font-semibold tracking-wider" style={{ color: 'var(--text-muted)' }}>{label}</div>
        <div className="font-bold text-sm" style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>
          {index.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </div>
      </div>
      <div className="flex items-center gap-1 ml-auto">
        {up ? <TrendingUp size={14} color="#00d26a" /> : <TrendingDown size={14} color="#ff3b30" />}
        <span className="text-xs font-bold" style={{ fontFamily: 'var(--font-mono)', color: up ? 'var(--accent-green)' : 'var(--accent-red)' }}>
          {up ? '+' : ''}{changePct.toFixed(1)}%
        </span>
      </div>
    </motion.div>
  );
}

// Ticker tape data
const TICKER_ITEMS = [
  { label: 'KOSPI', value: '2,650.12', change: '+0.8%', up: true },
  { label: 'KOSDAQ', value: '870.45', change: '+1.2%', up: true },
  { label: 'S&P 500', value: '5,920.30', change: '-0.3%', up: false },
  { label: 'NASDAQ', value: '19,250.10', change: '-0.5%', up: false },
  { label: 'NVDA', value: '$875.42', change: '+3.8%', up: true },
  { label: '삼성전자', value: '₩72,500', change: '+2.3%', up: true },
  { label: 'META', value: '$512.35', change: '+2.1%', up: true },
  { label: 'SK하이닉스', value: '₩185,000', change: '+3.1%', up: true },
  { label: 'TSLA', value: '$265.30', change: '+5.2%', up: true },
  { label: 'AMD', value: '$118.60', change: '+4.5%', up: true },
  { label: 'DOW', value: '42,850.20', change: '+0.4%', up: true },
  { label: 'USD/KRW', value: '1,328.50', change: '-0.2%', up: false },
];

export default function Header({ marketSummary, updatedAt }: Props) {
  const date = new Date(updatedAt);
  const formatted = date.toLocaleString('ko-KR', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  });

  const tickerItems = [...TICKER_ITEMS, ...TICKER_ITEMS];

  return (
    <header style={{ borderBottom: '1px solid var(--border-subtle)' }}>
      {/* Ticker Tape */}
      <div
        className="overflow-hidden py-2"
        style={{ background: 'rgba(0,0,0,0.4)', borderBottom: '1px solid var(--border-subtle)' }}
      >
        <div className="ticker-tape flex items-center gap-8 px-4">
          {tickerItems.map((item, i) => (
            <span key={i} className="flex items-center gap-2 shrink-0">
              <span className="text-xs tracking-wider" style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                {item.label}
              </span>
              <span className="text-xs font-semibold" style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
                {item.value}
              </span>
              <span className="text-xs font-bold" style={{ fontFamily: 'var(--font-mono)', color: item.up ? 'var(--accent-green)' : 'var(--accent-red)' }}>
                {item.change}
              </span>
              <span style={{ color: 'var(--text-muted)' }}>·</span>
            </span>
          ))}
        </div>
      </div>

      {/* Main Header */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-4">
        <div className="flex flex-col lg:flex-row items-start lg:items-center gap-4">
          {/* Logo */}
          <div className="flex items-center gap-3 shrink-0">
            <div
              className="w-9 h-9 rounded-xl flex items-center justify-center"
              style={{
                background: 'linear-gradient(135deg, rgba(0,210,106,0.25), rgba(0,255,204,0.1))',
                border: '1px solid rgba(0,210,106,0.35)',
                boxShadow: '0 0 15px rgba(0,210,106,0.2)',
              }}
            >
              <Activity size={18} color="#00d26a" />
            </div>
            <div>
              <div
                className="font-bold text-lg tracking-widest leading-none"
                style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent-green)', textShadow: '0 0 10px rgba(0,210,106,0.3)' }}
              >
                SIGNAL DECK
              </div>
              <div className="text-xs mt-0.5" style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                마지막 업데이트: {formatted}
              </div>
            </div>
          </div>

          {/* Market Summary Cards + Reels Link */}
          <div className="flex flex-wrap gap-3 lg:ml-auto items-center">
            <MarketCard label="KOSPI" index={marketSummary.kospi.index} changePct={marketSummary.kospi.change_pct} />
            <MarketCard label="KOSDAQ" index={marketSummary.kosdaq.index} changePct={marketSummary.kosdaq.change_pct} />
            <MarketCard label="S&P 500" index={marketSummary.sp500.index} changePct={marketSummary.sp500.change_pct} />
            <MarketCard label="NASDAQ" index={marketSummary.nasdaq.index} changePct={marketSummary.nasdaq.change_pct} />
            <motion.a
              href="/stock-screener/reels"
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              whileHover={{ scale: 1.05 }}
              className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold"
              style={{
                background: 'linear-gradient(135deg, rgba(123,47,247,0.25), rgba(0,212,255,0.15))',
                border: '1px solid rgba(123,47,247,0.45)',
                color: '#b47fff',
                textDecoration: 'none',
                boxShadow: '0 0 12px rgba(123,47,247,0.2)',
              }}
            >
              <Film size={15} />
              Reels
            </motion.a>
          </div>
        </div>
      </div>
    </header>
  );
}
