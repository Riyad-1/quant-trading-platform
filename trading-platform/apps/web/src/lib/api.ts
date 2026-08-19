import axios from 'axios'

export const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export const api = axios.create({
  baseURL: API_URL,
  timeout: 120_000,
  headers: { 'Content-Type': 'application/json' },
})

export function apiErrorMessage(error: unknown) {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail
    return typeof detail === 'string' ? detail : error.message
  }
  return error instanceof Error ? error.message : 'Unexpected request failure'
}

export interface HealthResponse {
  status: string
  database: string
  redis?: string
}

export interface StockScore {
  ticker: string
  company_name: string
  sector: string
  industry: string
  price: number
  composite_score: number
  momentum_score: number
  breakout_score: number
  relative_strength_score: number
  volume_score: number
  fundamentals_score: number
  market_compatibility_score: number
  setup_type: string
  confidence: string
  rank: number
  timestamp: string
}

export interface ScannerProviderStatus {
  configured_provider: string
  active_source: string
  fallback_source: string | null
  openbb_data_provider: string | null
  openbb_url: string | null
  last_error: string | null
  default_universe_size: number
  live_market_data: boolean
}

export interface RegimeResponse {
  date: string
  regime: string
  confidence: number
  spy_trend: string
  vix_level: string
  breadth_score: number
  volatility_regime: string
  risk_score: number
  strategy_recommendations: Record<string, string>
}

export interface BacktestMetricSet {
  final_equity: number
  roi: number
  cagr: number
  max_drawdown: number
  volatility: number
  sharpe_zero_rf: number
}

export interface BacktestResult {
  ticker: string
  strategy_name: string
  data_source: string
  start_date: string
  end_date: string
  initial_capital: number
  commission_bps: number
  slippage_bps: number
  execution: string
  strategy: BacktestMetricSet
  benchmark: BacktestMetricSet
  excess_roi: number
  entries: number
  exits: number
  market_exposure: number
  equity_curve: Array<{ date: string; strategy: number; benchmark: number }>
  limitations: string[]
}

export interface NewsArticle {
  id: number
  headline: string
  summary: string | null
  published_at: string
  url: string | null
  tickers: string[]
  is_processed: boolean
}

export interface Portfolio {
  id: number
  name: string
  initial_cash: number
  current_cash: number | null
  total_equity: number | null
  created_at: string
  updated_at: string
}

export interface PortfolioPosition {
  id: number
  asset_id: number
  quantity: number
  entry_price: number
  entry_date: string
  status: string
  pnl_realized: number | null
}

export interface PortfolioSnapshot {
  time: string
  equity: number | null
  cash: number | null
  exposure: number | null
}

export interface PaperPosition {
  ticker: string
  quantity: number
  avg_cost: number
  current_price: number
  market_value: number
  unrealized_pnl: number
  unrealized_pnl_pct: number
}

export interface PaperSummary {
  initial_capital: number
  cash: number
  positions_value: number
  total_value: number
  total_pnl: number
  total_pnl_pct: number
  num_positions: number
  num_pending_orders: number
  num_closed_trades: number
  sector_exposure: Record<string, number>
  positions: PaperPosition[]
  pending_orders: Array<Record<string, unknown>>
  recent_trades: Array<Record<string, unknown>>
  persistence: string
  notice: string
}

export interface MLStatus {
  status: string
  supported_models: string[]
  training_mode: string
  registered_models: number
  active_models: number
  notice: string
}

export interface ModelMetadata {
  model_id: string
  model_type: string
  horizon_days: number
  trained_at: string
  val_auc: number
  val_accuracy: number
  feature_count: number
  is_active: boolean
}
