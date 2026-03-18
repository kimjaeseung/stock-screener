# TopStockDaily Reels — 구현 체크리스트

## 🎯 최종 목표

브라우저에서 열면 30초짜리 주식 스윙 트레이딩 릴스가
자동 재생되고, 화면 녹화하면 바로 인스타 릴스로 올릴 수 있어야 함.

핵심 콘셉트:
"오늘 이 가격에 사서, 이 가격 지켜주면, 4주 안에 여기까지"
보는 사람이 바로 따라할 수 있는 구체적 액션 제시.

결과물 기준:
- 버튼 없음. 열면 자동재생.
- 30초 후 자동 루프.
- Chart.js 없음. 순수 Canvas API.
- 외부 JS 없음. Google Fonts만 허용.
- data.json 없어도 목데이터로 동작.
- 지표 이름 화면 표시 금지. 의미로만 설명.
- 탭하면 일시정지/재생 토글만.

## 📐 레이아웃

phone: 390×844px, background #050505
모바일: width 100vw, height 100dvh

## 🎨 디자인 토큰

--gold:  #f59e0b
--green: #10b981
--red:   #ef4444
--blue:  #60a5fa
--bg:    #050505
--bg2:   #0a0a0a
--bg3:   #111111

## ⏱ 씬 타임라인 (총 30초)

| 씬  | 타입         | 종목 | 시작    | 길이   |
|-----|-------------|------|---------|--------|
| S0  | hook        | 1    | 0ms     | 2500ms |
| S1  | entry_card  | 1    | 2500ms  | 3000ms |
| S2  | chart       | 1    | 5500ms  | 4500ms |
| S3  | summary     | 1    | 10000ms | 3500ms |
| SX  | transition  | -    | 13500ms | 500ms  |
| S4  | hook        | 2    | 14000ms | 2500ms |
| S5  | entry_card  | 2    | 16500ms | 3000ms |
| S6  | chart       | 2    | 19500ms | 4500ms |
| S7  | summary     | 2    | 24000ms | 3500ms |
| S8  | final       | -    | 27500ms | 2500ms |

## 🎬 씬별 상세 시나리오

### S0/S4 — 후킹 씬 (2500ms)
배경: 완전 검정. 텍스트만.
- 0ms    → "오늘의 스윙 기회" (11px, #f59e0b, 자간 0.4em) fadeIn
- 600ms  → "4주 안에 +{target2_pct}% 가능" (36px, white, 700) slideUp
- 1200ms → "{TICKER}" (72px, #f59e0b, 900) 황금 플래시 + easeOutElastic
- 1600ms → "{sector} · NASDAQ" (12px, #444) fadeIn

### S1/S5 — 진입 조건 카드 (3000ms)
- 0ms    → 전체 카드 아래서 위로 슬라이드인 (600ms, easeOutCubic)
- 200ms  → 종목명/가격/등락률 행 등장
- 300ms  → 진입가 행 (금색 테두리 펄싱)
- 400ms  → 손절가 행 (빨간색)
- 500ms  → 목표1 행 (초록색)
- 600ms  → 목표2 행 (연초록)
- 700ms  → 손익비 행 (2.0이상=금색+⭐)
- 1500ms → "이 가격대 지켜주면 홀드" 문구 fadeIn
- 1700ms → "손절가 이탈 시 즉시 매도" 문구 fadeIn

### S2/S6 — 차트 근거 (4500ms)
Canvas 2D. 패딩 {T:14, R:54, B:24, L:8}
- 0~1200ms    → 가격 라인 혜성 효과로 그려짐 + 일목 구름 fadeIn
- 1200~2200ms → 피보나치 38.2/50/61.8% 수평선 순차 등장
                진입가 구간 황금 하이라이트
                "핵심 지지구간 진입 중" popLabel
- 2200~3000ms → 골든크로스 지점 황금 drawBurst()
                MA5/MA20 라인
                "단기 모멘텀 켜짐 ✓" popLabel
- 3000~3800ms → 거래량 바 아래서 위로 easeOutQuint
                스파이크 바 초록 펄싱
                "거래량 {X}배 수급 확인 ✓" popLabel
- 3800~4500ms → 손절가 빨간 점선 + "🛑 $XXX"
                목표가1 초록 실선 + "🎯 $XXX"
                목표가2 연초록 점선
                진입 구간 황금 반투명 박스
                "손익비 X:1" 뱃지 팍 등장

### S3/S7 — 스윙 조건 요약 (3500ms)
- 0ms    → "이 조건이면 진입" (18px, #f59e0b) fadeIn
- 100ms  → 신호1 오른쪽에서 슬라이드인
- 220ms  → 신호2
- 340ms  → 신호3
- 460ms  → 신호4
- 580ms  → 신호5
           (충족된 것만, 최대 5개, 의미로 표현)
- 1500ms → 손절/목표/손익비 카드 fadeIn
- 2200ms → 매수등급 버튼 scaleUp (easeOutElastic)
           score 80+ → "⭐ 강력 매수 신호" #f59e0b
           score 60+ → "👍 매수 신호" #10b981
           score 40+ → "⚠ 추가 관망" #444

### SX — 전환 (500ms)
- 흰색 플래시 (opacity 0→0.8→0)
- "다음 추천주 →" 오른쪽 스윕

### S8 — 마무리 (2500ms)
- 0ms   → "오늘의 스윙 픽" (금색) fadeIn
- 200ms → 종목1 카드 왼쪽에서 슬라이드인
- 400ms → 종목2 카드 오른쪽에서 슬라이드인
          각 카드: 티커/가격/진입/목표/손절/손익비
- 800ms → "저장해두고 직접 확인해보세요 📌" 깜빡임 시작
- 1200ms→ "TopStockDaily" (금색)
- 1400ms→ "⚠ 투자 참고용 · 손익 책임은 본인에게" (아주 작게)

## 🔧 신호 의미 매핑 (화면에 지표 이름 절대 표시 금지)

golden_cross      → "단기 상승 모멘텀 켜짐"
volume_confirm    → "거래량 {X}배 — 수급 확인"
rsi_signal        → "아직 과열 아님 — 상승 여력 있음"
rsi_divergence    → "하락 중 매수세 증가"
bollinger_break   → "눌려있던 변동성 폭발"
macd_cross        → "매수세가 매도세를 이겼습니다"
stoch_signal      → "과매도 구간 탈출 — 반등 시작"
ma_alignment      → "모든 추세가 위를 향하고 있습니다"
relative_strength → "나스닥 빠질 때도 혼자 버팀"
fib_support       → "핵심 피보나치 지지선 반등"
ichimoku_bull     → "구름 위 강세 구간 진입"

## ✅ 구현 체크리스트

### 기반 세팅
- [x] 1. HTML 껍데기 (#phone, #segbar, #scene-canvas, #ui-layer)
- [x] 2. Canvas 초기화 (DPR 처리)
- [x] 3. 이징 함수 (easeOutCubic, easeOutQuint, easeOutElastic, lerp, clamp, prog)
- [x] 4. 세그먼트 프로그레스바 (buildSegBar, updateSegBar)
- [x] 5. data.json 로더 + 목데이터

### 씬 엔진
- [x] 6. 마스터 루프 (rAF, 씬 전환, 탭 토글, 자동루프)
- [x] 7. 씬 렌더 디스패처 (renderScene → 타입별 분기)

### Canvas 유틸
- [x] 8. drawCometLine() — 혜성 라인
- [x] 9. drawBurst() — 폭발 (플래시+링+파티클+글로우)
- [x] 10. drawPopLabel() — 팝업 레이블

### 씬 구현
- [x] 11. 후킹 씬 (텍스트 순차 등장 + 황금 플래시)
- [x] 12. 진입 조건 카드 씬 (슬라이드인 + 펄싱)
- [x] 13. 차트 씬 — 가격선 혜성 + 일목 구름
- [x] 14. 차트 씬 — 피보나치 수평선
- [x] 15. 차트 씬 — 골든크로스 폭발
- [x] 16. 차트 씬 — 거래량 바
- [x] 17. 차트 씬 — 목표가/손절가 수평선
- [x] 18. 스윙 조건 요약 씬
- [x] 19. 전환 씬
- [x] 20. 마무리 씬

### 통합
- [x] 21. 전체 30초 자동재생 + 루프 검증
- [x] 22. data.json 실데이터 연동 검증 (prepareData 방어 전처리 포함)
- [x] 23. 최종 점검 (콘솔 에러 0, 모바일 레이아웃, GitHub Pages)
