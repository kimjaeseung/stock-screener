# 알고리즘 감사 보고서

**날짜:** 2026-03-18

---

## STEP 1 — 파일 구조 요약

### scripts/ 폴더

| 파일 | 역할 요약 |
|------|-----------|
| `scripts/indicators.py` | pandas_ta 기반 기술적 지표 계산(SMA/EMA/RSI/MACD/BB/ATR/ADX/스토캐스틱), 피보나치 레벨, 스윙 포인트, 거래량 비율, BB 위치/폭 백분위 |
| `scripts/scoring.py` | 100점 만점 스코어링(추세/골든크로스/모멘텀/거래량/지지/볼린저), indicators 모듈 의존 |
| `scripts/screener.py` | 메인 스크리너: 자체 구현 지표(_sma/_ema/_rsi/_macd/_bbands/_atr/_adx/_stoch), 점수·R:R·차트패턴·한국/미국 유니버스·yfinance 연동, CLI 진입점 |
| `scripts/risk_reward.py` | 손익비 계산(진입/손절/목표), 스윙·피보나치·ATR·BB 활용, 2:1 미만 시 None |
| `scripts/requirements.txt` | yfinance, finance-datareader, pandas, numpy, requests, beautifulsoup4, lxml, httpx 의존성 |
| `scripts/tsd/data_fetcher.py` | yfinance Ticker.history()로 단일/배치 OHLCV 조회, 동기 fetch_all_sync |
| `scripts/tsd/top100.py` | Finviz NASDAQ Top 100 스크래핑(거래량·가격 기준), 24시간 캐시, fallback 목록 |
| `scripts/tsd/screener.py` | 9개 시그널 수동 계산(골든크로스·거래량·RSI·MACD·BB스퀴즈·스토캐스틱·52주고가·5일모멘텀·상대강도), run_screener로 상위 N개 반환 |
| `scripts/tsd/run.py` | TopStockDaily 파이프라인: top100 → fetch_all_sync → run_screener → docs/data.json 저장, SPY 20일 수익률 조회 |

### .github/workflows/

| 파일 | 역할 요약 |
|------|-----------|
| `deploy.yml` | main 푸시 또는 Daily Stock Update 완료 시 빌드 후 GitHub Pages 배포, docs/index.html·data.json을 dist/reels로 복사 |
| `daily-update.yml` | 평일 UTC 20:30·21:30 cron으로 스크리너 실행(tsd/run.py), docs/data.json 커밋·푸시 |
| `screener.yml` | 평일 UTC 07:30·22:30 cron(한국/미국 장 마감 후), scripts/screener.py 전체 스캔, public/data/ 커밋·푸시 |

### docs/

| 파일 | 역할 요약 |
|------|-----------|
| `docs/data.json` | TopStockDaily 결과(updated_at, spy_20d, top100_count, stocks). 현재 top100_count=0, stocks=[] |

---

## STEP 2 — 알고리즘 정확성 감사 요약

(상세는 아래 🔴🟡🟢 섹션에 반영)

---

## STEP 3 — 데이터 파이프라인 감사 요약

(상세는 아래 🔴🟡🟢 섹션에 반영)

---

# 종합 결과

## 🔴 심각한 문제 (즉시 수정 필요)

### 1. tsd/screener.py — 거래량 비율 계산 오류 (당일 포함 평균)
- **위치:** `scripts/tsd/screener.py` 80행, 98행
- **내용:** `avg_vol_20 = float(volume.tail(20).mean())` → **당일을 포함한 최근 20일 평균**을 사용함. 표준은 “당일 거래량 vs 직전 20일 평균(당일 제외)”.
- **영향:** 거래량 급증 시 평균이 올라가 비율이 낮게 나와 시그널 누락/왜곡 가능.
- **수정:** `volume.iloc[-21:-1].mean()` 또는 동일 의미로 직전 20일만 사용.

### 2. tsd/screener.py — “골든크로스”가 실제로는 단순 MA 비교
- **위치:** `scripts/tsd/screener.py` 89–95행
- **내용:** `if float(ma20.iloc[-1]) > float(ma60.iloc[-1])` 만 검사. **전일 MA20 ≤ MA60이고 오늘 MA20 > MA60인 “돌파” 조건이 아님.**
- **영향:** 이미 정배열인 구간도 골든크로스로 점수 부여 → 과다 점수, 잘못된 신호.
- **수정:** 최근 N일 루프에서 `ma20.iloc[i-1] <= ma60.iloc[i-1] and ma20.iloc[i] > ma60.iloc[i]` 형태로 진짜 크로스만 감지.

### 3. scripts/screener.py·tsd/screener.py — 볼린저 밴드 표준편차 ddof
- **위치:** `scripts/screener.py` 43행, `scripts/tsd/screener.py` 39행
- **내용:** `s.rolling(n).std()` 사용 → pandas 기본 **ddof=1(표본 표준편차)**. 볼린저 밴드 표준은 **모집단 표준편차(ddof=0)**.
- **영향:** 밴드가 약간 넓게 나와 스퀴즈/돌파 판단이 표준과 어긋남.
- **수정:** `s.rolling(n).std(ddof=0)` 적용.

### 4. tsd/screener.py — RSI가 Wilder's smoothing 미적용
- **위치:** `scripts/tsd/screener.py` 20–25행
- **내용:** `gain = delta.clip(lower=0).rolling(n).mean()`, `loss = (-delta.clip(upper=0)).rolling(n).mean()` → **단순 이동평균**. RSI 표준은 **Wilder's smoothing(EMA, α=1/n)**.
- **영향:** RSI 값이 표준 구현·다른 차트와 불일치, 과매수/과매도 구간 해석 오류 가능.
- **수정:** `ewm(alpha=1/n, adjust=False).mean()` 또는 `ewm(span=n, adjust=False).mean()` 사용 (screener.py의 _rsi와 동일 방식).

### 5. Yahoo Finance — rate limit(429)·타임아웃·재시도 미구현
- **위치:** `scripts/tsd/data_fetcher.py`, `scripts/screener.py` (yf.download / Ticker.history)
- **내용:** 429 에러 시 재시도, 요청별 타임아웃 설정 없음. 대량 티커 시 차단·실패 가능.
- **영향:** 배치 실행 시 일부 종목 누락·전체 실패 가능.
- **수정:** 요청당 timeout 명시, 429 시 exponential backoff 재시도, 배치 간 sleep 유지(이미 일부 있음).

---

## 🟡 개선 필요 (정확도 영향)

### 1. 윈도우 크기 > 데이터 길이 시 예외 처리
- **위치:** `scripts/indicators.py`는 `len(df) < 60`만 검사. pandas_ta 호출 시 length=120/200 등이 있으면 초반 구간 NaN만 많아질 뿐이라 크래시는 아니나, **scripts/screener.py**·**tsd/screener.py**의 rolling(n)은 n이 길이 초과 시 동작만 하고 의미 없는 값이 나올 수 있음.
- **권장:** 지표별 필요 봉 수(예: MA200→200, MACD→26+)를 문서화하고, `len(df) < required_bars`이면 해당 지표/스코어 스킵 또는 None 반환.

### 2. RSI 0으로 나누기
- **screener.py:** `l + 1e-10`으로 방지됨.
- **tsd/screener.py:** `loss + 1e-9`로 방지됨.
- **indicators.py:** pandas_ta 위임. pandas_ta 내부는 별도 확인 필요. 전반적으로 **명시적 0/NaN 체크 후 None 반환**이 있으면 더 안전함.

### 3. 스토캐스틱 high_n == low_n
- **screener.py:** `(hi - lo + 1e-10)` 사용 → 0 나누기 방지.
- **tsd/screener.py:** `(highest_high - lowest_low + 1e-9)` 사용 → 동일.
- **추가 권장:** 결과가 0/100으로 고정되는 구간을 “변동 없음”으로 처리해 스코어에서 제외하거나 별도 플래그.

### 4. 피보나치 — 스윙 고/저 미사용
- **위치:** `scripts/indicators.py` `calculate_fibonacci()`
- **내용:** `recent['High'].max()`, `recent['Low'].min()` 사용 → **구간 내 단순 고/저**. 진짜 피보나치 되돌림은 **스윙 하이/스윙 로우** 기준이 표준.
- **영향:** 횡보 구간에서 범위가 왜곡되어 38.2~61.8% 구간 판단이 부정확해질 수 있음.
- **권장:** `find_swing_points()`와 연동해 swing_high/swing_low 기반 피보나치 레벨 계산 옵션 추가.

### 5. 일목균형표·RSI 다이버전스 미구현
- **일목균형표:** 전환선/기준선/선행스팬 A·B 등 **구현 없음**. 감사 항목만 존재.
- **RSI 다이버전스:** “가격 저점 하락 + RSI 저점 상승” 등 **진짜 다이버전스 로직 없음**. 별도 스코어/시그널 없음.
- **권장:** 필요 시 일목/다이버전스 요구사항을 명시하고, 구현 시 스윙 로우/하이 감지 후 비교하도록 설계.

### 6. data_fetcher — OHLCV 길이 불일치 미처리
- **위치:** `scripts/tsd/data_fetcher.py`
- **내용:** Close, Volume만 dropna 후 필터. **날짜 인덱스 기준으로 Open/High/Low와 길이 불일치** 시 한 컬럼만 짧아질 수 있음.
- **권장:** 필수 컬럼 전부 존재하는 행만 남기거나, 인덱스 기준 정렬 후 앞쪽 결측 제거해 길이 통일.

### 7. tsd 파이프라인 — 최소 봉 수 불일치
- **data_fetcher:** `len(df) >= 20`만 요구.
- **tsd/screener.py:** `len(df) >= 60` 요구.
- **MACD(26), MA60(60), 52주 고가(252)** 등은 60일로는 부족. 252일은 6개월 데이터로는 부족할 수 있음.
- **권장:** period='6mo' 대신 '1y' 이상 사용하거나, 필요 봉 수를 명시하고 부족 시 해당 지표/점수만 비활성화.

---

## 🟢 개선 권장 (선택사항)

### 1. indicators.py — pandas_ta 의존성
- **현재:** `scripts/indicators.py`만 pandas_ta 사용. `screener.py`는 자체 구현.
- **권장:** 지표 구현을 한 곳으로 통일하면 유지보수·검증이 쉬움. pandas_ta 통일 또는 자체 구현 통일 중 선택.

### 2. 종합 점수 — 가중치·핵심 신호 필터
- **현재:** 배점은 구간별로 나뉘어 있으나, “거래량 급증/골든크로스가 없으면 상위 노출 제한” 같은 **필수 조건 필터**는 없음. checklist는 있으나 필터로 쓰이지 않음.
- **권장:** 점수만 높고 거래량·골든크로스가 모두 없으면 순위에서 감점하거나 제외하는 옵션 검토.

### 3. Finviz top100 — rate limit·캐시
- **현재:** `time.sleep(0.5)` 존재. 캐시 TTL 24시간.
- **권장:** 429/5xx 시 재시도, 실패 시 이전 캐시가 있으면 그대로 반환하는 fallback 유지(현재는 파싱 실패 시 하드코딩 목록 반환).

### 4. GitHub Actions cron
- **daily-update.yml:** `30 20 * * 1-5` (UTC 20:30) → 미국 동부 기준 **장 마감 전**(나스닥 16:00 ET = 21:00 UTC). `30 21 * * 1-5`는 마감 후 맞음.
- **권장:** 20:30은 “마감 직전”으로 두고, 완료 데이터만 쓰려면 21:30 단일 cron 또는 22:00으로 통일 검토.

### 5. 실패 시 알림
- **현재:** 워크플로 실패 시 GitHub 알림 외 별도 알림 없음.
- **권장:** 실패 시 Slack/이메일 등 알림 추가 시 운영 안정성 향상.

---

## ✅ 올바르게 구현된 것

### 1. scripts/screener.py — RSI (Wilder's)
- `ewm(com=n-1, adjust=False).mean()` 사용 → Wilder's smoothing과 동일.

### 2. scripts/screener.py — 골든크로스 감지
- `ma5.iloc[i-1] < ma20.iloc[i-1] and ma5.iloc[i] >= ma20.iloc[i]` 등으로 **진짜 돌파**만 인정.

### 3. scripts/screener.py — 거래량 비교
- `vol_20d_avg = v_ser.iloc[-21:-1].mean()`, `vol_current = v_ser.iloc[-1]` → **당일 제외 20일 평균** vs 당일.

### 4. scripts/indicators.py — get_volume_ratio
- `tail(period+1).head(period).mean()` → 직전 20일 평균, `iloc[-1]` → 당일. 올바름.

### 5. scripts/indicators.py — get_bb_position
- `band_width == 0`일 때 0.5 반환 → 변동 없을 때 예외 처리 있음.

### 6. MACD
- **screener.py / tsd/screener.py:** EMA(12)−EMA(26), Signal=EMA(9) of MACD, Histogram=MACD−Signal. 정의와 일치.

### 7. 스토캐스틱
- %K = (close−low_n)/(high_n−low_n)*100, %D = SMA(3) of %K. high−low 0 방지용 소량 엡실론 사용 적절.

### 8. scripts/screener.py — 당일 미완료 데이터 제거
- `df.index[-1].date() == today`이면 마지막 행 제거 후 130일 재검사. 장중 partial 제거 로직 적절.

### 9. indicators.py — pandas_ta BB
- pandas_ta bbands는 기본 ddof=0(모집단 표준편차) 사용. 표준과 일치.

### 10. 상대강도(20일 수익률 vs 벤치마크)
- screener.py: 20일 수익률과 SPY(또는 ^KS11) 20일 수익률 차이로 보너스. 비교 기간·정규화 적절.

### 11. Finviz top100
- 24시간 캐시, 파싱 실패 시 하드코딩 fallback, ticker 검증, `time.sleep(0.5)`로 요청 간격 확보.

---

## 📋 수정 우선순위

1. **tsd/screener.py 거래량 비율** — 당일 제외 20일 평균으로 변경 (`iloc[-21:-1].mean()`).
2. **tsd/screener.py 골든크로스** — “MA20 > MA60”이 아니라 “전일 이하 & 오늘 초과” 크로스 조건으로 변경.
3. **tsd/screener.py RSI** — Wilder's smoothing(ewm) 적용.
4. **볼린저 ddof=0** — screener.py·tsd/screener.py의 `rolling(n).std()`에 `ddof=0` 추가.
5. **Yahoo Finance** — 요청 timeout 설정 + 429 시 재시도(backoff) 도입.
6. **tsd 데이터 기간/최소 봉** — 1y 또는 필요 봉 수 명시 후, MACD/52주 고가 등이 유효하도록 조정.
7. **피보나치** — 선택적으로 스윙 high/low 기반 레벨 추가.
8. **지표별 최소 봉 수** — 문서화 및 부족 시 해당 지표/점수 스킵 처리.

---

---

## 🔧 반영 완료 (2026-03-18)

| 항목 | 수정 파일 | 내용 |
|------|-----------|------|
| 거래량 비율 당일 제외 | tsd/screener.py | avg_vol_20 = volume.iloc[-21:-1].mean(), vol_ratio = 당일/직전20일평균 |
| 골든크로스 실제 돌파 감지 | tsd/screener.py | 최근 10일 루프로 전일 ≤ & 당일 > 조건 만족 시에만 +15점 |
| RSI Wilder's smoothing | tsd/screener.py | gain/loss에 ewm(alpha=1/n, adjust=False).mean() 적용 |
| 볼린저 ddof=0 | screener.py, tsd/screener.py | rolling(n).std(ddof=0) 적용 |
| Yahoo 429 재시도·타임아웃 | tsd/data_fetcher.py | 최대 3회 재시도, exponential backoff, timeout 30s (미지원 시 생략) |
| 데이터 기간 1년 | tsd/run.py | fetch_all_sync(period="1y")로 52주 고가 등 유효화 |

*본 보고서는 scripts/ 및 .github/workflows/, docs/data.json 기준으로 작성되었습니다.*
