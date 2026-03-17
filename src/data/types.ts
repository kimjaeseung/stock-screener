export interface MarketIndex {
  index: number;
  change_pct: number;
}

export interface MarketSummary {
  kospi: MarketIndex;
  kosdaq: MarketIndex;
  sp500: MarketIndex;
  nasdaq: MarketIndex;
}

export interface ScoreBreakdown {
  trend: number;
  golden_cross: number;
  momentum: number;
  volume: number;
  support: number;
  bollinger: number;
}

export interface Technicals {
  rsi_14: number;
  macd: number;
  macd_signal: number;
  adx: number;
  volume_ratio: number;
  bb_position: number;
}

export interface RiskReward {
  entry: number;
  stop_loss: number;
  take_profit: number;
  risk: number;
  reward: number;
  ratio: number;
  risk_pct: number;
  reward_pct: number;
}

export interface Checklist {
  above_ma200: boolean;
  golden_cross_recent: boolean;
  volume_surge: boolean;
  rsi_healthy: boolean;
  macd_bullish: boolean;
  trend_strong: boolean;
  rr_ratio_good: boolean;
}

export interface StockResult {
  rank: number;
  ticker: string;
  name: string;
  market: string;
  sector: string;
  price: number;
  change_pct: number;
  score: number;
  score_breakdown: ScoreBreakdown;
  signals: string[];
  technicals: Technicals;
  risk_reward: RiskReward;
  price_history_30d: number[];
  ma_20: number;
  ma_60: number;
  checklist: Checklist;
}

export interface ScreeningResults {
  kr: StockResult[];
  us: StockResult[];
}

export interface ScreeningData {
  updated_at: string;
  market_summary: MarketSummary;
  screening_results: ScreeningResults;
}

export type MarketTab = 'kr' | 'us';
