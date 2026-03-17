import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronDown, Activity, TrendingUp, BarChart2, Layers, Target, Zap } from 'lucide-react';

const METHODS = [
  {
    icon: TrendingUp,
    title: '추세 조건 (Trend)',
    subtitle: '최대 25점',
    color: '#00d26a',
    items: [
      '이평선 정배열 (5>20>60>120): +10점',
      '주가가 200일선 위: +5점',
      'ADX > 25 (강한 추세): +5점',
      '20일선 기울기 양수: +5점',
    ],
    desc: '이동평균선(Moving Average)의 정배열은 단기→중기→장기 순으로 주가가 위치하여 상승 추세가 형성된 상태. ADX(Average Directional Index)는 추세의 강도를 0~100으로 나타냄.',
  },
  {
    icon: Zap,
    title: '골든크로스 / 추세 전환 (Golden Cross)',
    subtitle: '최대 20점',
    color: '#f5a623',
    items: [
      '5일선 20일선 골든크로스 (최근 5일 이내): +10점',
      '20일선 60일선 골든크로스 (최근 10일 이내): +10점',
      'MACD 골든크로스 (최근 3일 이내): +10점',
    ],
    desc: '골든크로스는 단기 이동평균선이 장기 이동평균선을 상향 돌파하는 것으로, 추세 전환 또는 상승 가속의 신호. MACD(이동평균 수렴/발산)의 크로스도 동일한 의미.',
  },
  {
    icon: Activity,
    title: '모멘텀 & 오실레이터 (Momentum)',
    subtitle: '최대 20점',
    color: '#58a6ff',
    items: [
      'RSI 40~60 구간 (적정 구간): +5점',
      'RSI 30 이하에서 반등 (과매도 탈출): +10점',
      '스토캐스틱 %K가 %D 상향 돌파: +5점',
      'MACD 히스토그램 증가 추세: +5점',
    ],
    desc: 'RSI(상대강도지수)는 과매수(>70)/과매도(<30)를 판단. 스토캐스틱은 현재 가격이 최근 고점/저점 범위에서 어디에 있는지 보여주는 모멘텀 지표.',
  },
  {
    icon: BarChart2,
    title: '거래량 시그널 (Volume)',
    subtitle: '최대 15점',
    color: '#bc8cff',
    items: [
      '거래량 비율 ≥ 2.0 (20일 평균 대비): +10점',
      '거래량 비율 ≥ 1.5: +5점',
      '거래량 증가 + 주가 상승 (수급 일치): +5점',
    ],
    desc: '거래량은 가격 움직임의 신뢰도를 측정. 가격 상승 시 거래량이 함께 증가하면 수급이 실제로 뒷받침된다는 의미로 신호의 신뢰도가 높음.',
  },
  {
    icon: Target,
    title: '지지/저항 & 피보나치 (Support)',
    subtitle: '최대 10점',
    color: '#00ffcc',
    items: [
      '피보나치 38.2%~61.8% 구간 반등: +5점',
      '볼린저 하단 근처에서 반등: +5점',
      '20일선 또는 60일선에서 지지 확인: +5점',
    ],
    desc: '피보나치 되돌림은 추세 움직임의 38.2%, 50%, 61.8% 지점이 강한 지지/저항 역할을 한다는 이론. 볼린저 밴드 하단 반등은 평균 회귀 신호.',
  },
  {
    icon: Layers,
    title: '볼린저 밴드 스퀴즈 (Bollinger)',
    subtitle: '최대 10점',
    color: '#ff9500',
    items: [
      'BB 폭이 최근 120일 중 하위 20% (스퀴즈 상태): +5점',
      '스퀴즈 후 상단 돌파 시작: +10점',
    ],
    desc: '볼린저 밴드 폭이 좁아지는 스퀴즈 상태는 변동성이 압축된 것. 스퀴즈 이후 상단 돌파는 강력한 상승 돌파 신호로 해석.',
  },
];

export default function Methodology() {
  const [open, setOpen] = useState<number | null>(null);

  return (
    <section className="max-w-7xl mx-auto px-4 sm:px-6 py-12">
      <div className="text-center mb-8">
        <h2 className="text-xl font-bold mb-2" style={{ color: 'var(--text-primary)' }}>스크리닝 기준 설명</h2>
        <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
          100점 만점 · 60점 이상 + 손익비 2:1 이상인 종목만 추천 대상
        </p>
      </div>

      <div className="space-y-2">
        {METHODS.map((method, i) => {
          const Icon = method.icon;
          const isOpen = open === i;
          return (
            <motion.div
              key={i}
              className="glass rounded-xl overflow-hidden"
              style={{ border: `1px solid ${isOpen ? method.color + '40' : 'var(--border-subtle)'}` }}
            >
              <button
                className="w-full flex items-center gap-4 p-4 text-left"
                onClick={() => setOpen(isOpen ? null : i)}
              >
                <div
                  className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0"
                  style={{ background: `${method.color}15`, border: `1px solid ${method.color}30` }}
                >
                  <Icon size={16} color={method.color} />
                </div>
                <div className="flex-1">
                  <div className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{method.title}</div>
                  <div className="text-xs mt-0.5" style={{ color: method.color }}>{method.subtitle}</div>
                </div>
                <motion.div animate={{ rotate: isOpen ? 180 : 0 }} transition={{ duration: 0.2 }}>
                  <ChevronDown size={16} color="var(--text-muted)" />
                </motion.div>
              </button>

              <AnimatePresence>
                {isOpen && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.3 }}
                  >
                    <div className="px-4 pb-4" style={{ borderTop: '1px solid var(--border-subtle)' }}>
                      <p className="text-sm pt-3 mb-3" style={{ color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                        {method.desc}
                      </p>
                      <div className="space-y-1">
                        {method.items.map((item, j) => (
                          <div key={j} className="text-sm flex items-start gap-2" style={{ color: 'var(--text-secondary)' }}>
                            <span className="mt-0.5 shrink-0" style={{ color: method.color }}>·</span>
                            {item}
                          </div>
                        ))}
                      </div>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>
          );
        })}
      </div>
    </section>
  );
}
