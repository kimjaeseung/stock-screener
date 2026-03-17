import { useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import IntroScreen from './components/IntroScreen';
import Header from './components/Header';
import StockCard from './components/StockCard';
import StockDetail from './components/StockDetail';
import Methodology from './components/Methodology';
import MatrixLoader from './components/MatrixLoader';
import { useScreeningData } from './hooks/useScreeningData';
import type { StockResult, MarketTab } from './data/types';
import { Github, AlertTriangle, Terminal } from 'lucide-react';

export default function App() {
  const [showIntro, setShowIntro] = useState(true);
  const [tab, setTab] = useState<MarketTab>('kr');
  const [selected, setSelected] = useState<StockResult | null>(null);
  const { data, loading } = useScreeningData();

  if (showIntro) {
    return <IntroScreen onComplete={() => setShowIntro(false)} />;
  }

  if (loading) {
    return <MatrixLoader />;
  }

  if (!data) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-grid" style={{ background: 'var(--bg-primary)' }}>
        <div
          className="text-center p-8 rounded-2xl max-w-md"
          style={{ background: 'rgba(22,27,34,0.8)', border: '1px solid rgba(245,166,35,0.3)', boxShadow: '0 0 30px rgba(245,166,35,0.1)' }}
        >
          <Terminal size={32} color="#f5a623" className="mx-auto mb-4" />
          <h2 className="text-lg font-bold mb-2" style={{ color: 'var(--text-primary)' }}>
            스크리닝 결과가 없습니다
          </h2>
          <p className="text-sm mb-4" style={{ color: 'var(--text-muted)', lineHeight: 1.6 }}>
            GitHub Actions를 실행하거나 로컬에서 스크리너를 실행해주세요.
          </p>
          <div
            className="text-xs rounded-xl p-4 text-left"
            style={{ background: 'rgba(0,0,0,0.4)', border: '1px solid rgba(255,255,255,0.06)', fontFamily: 'var(--font-mono)', color: 'var(--accent-green)', lineHeight: 2 }}
          >
            <div>pip install -r scripts/requirements.txt</div>
            <div>python scripts/screener.py --test</div>
          </div>
        </div>
      </div>
    );
  }

  const stocks = tab === 'kr' ? data.screening_results.kr : data.screening_results.us;

  return (
    <div className="min-h-screen bg-grid" style={{ background: 'var(--bg-primary)' }}>
      {/* Radial glow */}
      <div className="fixed inset-0 pointer-events-none" style={{
        background: 'radial-gradient(ellipse 80% 40% at 50% 0%, rgba(0,210,106,0.03) 0%, transparent 60%)',
      }} />

      <Header marketSummary={data.market_summary} updatedAt={data.updated_at} />

      {/* Disclaimer banner */}
      <div className="w-full py-2 px-4 flex items-center justify-center gap-2 text-xs"
        style={{ background: 'rgba(245,166,35,0.08)', borderBottom: '1px solid rgba(245,166,35,0.15)', color: 'rgba(245,166,35,0.8)' }}>
        <AlertTriangle size={12} />
        본 서비스는 기술적 분석 기반의 참고 자료이며, 투자 조언이 아닙니다. 모든 투자의 책임은 투자자 본인에게 있습니다.
      </div>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-8">
        {/* Market Tab */}
        <div className="flex items-center gap-3 mb-8">
          <div className="flex p-1 rounded-xl gap-1" style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid var(--border-subtle)' }}>
            {(['kr', 'us'] as MarketTab[]).map(t => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className="relative px-5 py-2 rounded-lg text-sm font-semibold transition-colors"
                style={{
                  color: tab === t ? '#0a0a0f' : 'var(--text-secondary)',
                  cursor: 'pointer',
                }}
              >
                {tab === t && (
                  <motion.div
                    layoutId="tab-bg"
                    className="absolute inset-0 rounded-lg"
                    style={{ background: 'var(--accent-green)' }}
                    transition={{ type: 'spring', stiffness: 400, damping: 30 }}
                  />
                )}
                <span className="relative z-10">{t === 'kr' ? '🇰🇷 한국' : '🇺🇸 미국'}</span>
              </button>
            ))}
          </div>
          <div className="text-sm" style={{ color: 'var(--text-muted)' }}>
            TOP 10 종목 —&nbsp;
            <span style={{ color: 'var(--text-secondary)' }}>
              {tab === 'kr' ? 'KOSPI + KOSDAQ' : 'S&P 500 + NASDAQ 100'}
            </span>
          </div>
        </div>

        {/* Stock Grid */}
        <AnimatePresence mode="wait">
          {stocks.length === 0 ? (
            <motion.div
              key="empty"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="text-center py-20"
            >
              <div className="text-4xl mb-4">📊</div>
              <p className="text-base mb-2" style={{ color: 'var(--text-secondary)' }}>
                {tab === 'kr' ? '한국' : '미국'} 스크리닝 결과가 없습니다
              </p>
              <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
                GitHub Actions가 실행되면 자동으로 업데이트됩니다
              </p>
            </motion.div>
          ) : (
            <motion.div
              key={tab}
              className="grid grid-cols-1 lg:grid-cols-2 gap-5"
              initial={{ opacity: 0, x: tab === 'kr' ? -30 : 30 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: tab === 'kr' ? 30 : -30 }}
              transition={{ duration: 0.3 }}
            >
              {stocks.map((stock, i) => (
                <StockCard
                  key={stock.ticker}
                  stock={stock}
                  index={i}
                  onSelect={setSelected}
                  isKr={tab === 'kr'}
                />
              ))}
            </motion.div>
          )}
        </AnimatePresence>
      </main>

      {/* Gradient divider */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-2">
        <div className="h-px" style={{ background: 'linear-gradient(90deg, transparent, var(--accent-cyan), transparent)', opacity: 0.3 }} />
      </div>

      {/* Methodology section */}
      <Methodology />

      {/* Footer */}
      <footer className="border-t py-8 px-4" style={{ borderColor: 'var(--border-subtle)' }}>
        <div className="max-w-7xl mx-auto">
          <div className="flex flex-col md:flex-row items-center justify-between gap-4">
            <div className="text-center md:text-left">
              <p className="text-sm font-semibold mb-1" style={{ color: 'var(--accent-red)' }}>
                ⚠️ 면책 고지
              </p>
              <p className="text-xs" style={{ color: 'var(--text-muted)', lineHeight: 1.6, maxWidth: 500 }}>
                본 서비스는 투자 조언이 아닙니다. 모든 분석은 과거 데이터 기반의 기술적 분석이며,
                미래 수익을 보장하지 않습니다. 모든 투자의 책임은 투자자 본인에게 있습니다.
              </p>
            </div>
            <div className="flex flex-col items-center md:items-end gap-2 text-xs" style={{ color: 'var(--text-muted)' }}>
              <div className="flex items-center gap-2">
                <span>데이터 출처: Yahoo Finance, KRX</span>
              </div>
              <a
                href="https://github.com/kimjaeseung/stock-screener"
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1.5 hover:text-white transition-colors"
              >
                <Github size={14} />
                GitHub
              </a>
              <span style={{ fontFamily: 'var(--font-mono)' }}>Signal Deck © 2026</span>
            </div>
          </div>
        </div>
      </footer>

      {/* Detail Modal */}
      <AnimatePresence>
        {selected && (
          <StockDetail
            stock={selected}
            onClose={() => setSelected(null)}
            isKr={tab === 'kr'}
          />
        )}
      </AnimatePresence>
    </div>
  );
}
