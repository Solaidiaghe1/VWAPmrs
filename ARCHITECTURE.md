# VWAPmrs Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         VWAP Mean Reversion Strategy                │
└─────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│                          CONFIGURATION LAYER                          │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  config.yaml → config.py → Config (dot-accessible object)    │   │
│  └─────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
                                    │
                                    ↓
┌──────────────────────────────────────────────────────────────────────┐
│                            DATA LAYER                                 │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  data_loader.py                                              │   │
│  │  • Load OHLCV data from CSV                                  │   │
│  │  • Validate data quality                                     │   │
│  │  • Detect gaps                                               │   │
│  │  → Returns: pd.DataFrame                                     │   │
│  └─────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
                                    │
                                    ↓
┌──────────────────────────────────────────────────────────────────────┐
│                         INDICATOR LAYER                               │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  indicators.py                                               │   │
│  │  • VWAP calculation (batch & incremental)                    │   │
│  │  • ATR calculation (with timeframe resampling)               │   │
│  │  • Rolling statistics (mean, std)                            │   │
│  │  • Z-score & % deviation calculation                         │   │
│  │  → Returns: float or pd.Series                               │   │
│  └─────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
                                    │
                                    ↓
┌──────────────────────────────────────────────────────────────────────┐
│                          STRATEGY LAYER                               │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  signal_engine.py                                            │   │
│  │  ┌──────────────────────────────────────────────────────┐   │   │
│  │  │  StrategyState (per symbol)                          │   │   │
│  │  │  • VWAP state (cum_pv, cum_vol)                      │   │   │
│  │  │  • Rolling statistics                                │   │   │
│  │  │  • Bar indexing                                      │   │   │
│  │  │  • Session timing                                    │   │   │
│  │  └──────────────────────────────────────────────────────┘   │   │
│  │                                                               │   │
│  │  ┌──────────────────────────────────────────────────────┐   │   │
│  │  │  generate_entry_signal()                             │   │   │
│  │  │  • Volume filters                                    │   │   │
│  │  │  • Time filters (skip open/close)                    │   │   │
│  │  │  • Cooldown checks                                   │   │   │
│  │  │  • Z-score or % deviation thresholds                 │   │   │
│  │  │  → Returns: "LONG" | "SHORT" | None                  │   │   │
│  │  └──────────────────────────────────────────────────────┘   │   │
│  │                                                               │   │
│  │  ┌──────────────────────────────────────────────────────┐   │   │
│  │  │  check_exit_signal()                                 │   │   │
│  │  │  • Stop loss (highest priority)                      │   │   │
│  │  │  • Time exits (EOD, max holding)                     │   │   │
│  │  │  • Signal exits (reversion to VWAP)                  │   │   │
│  │  │  → Returns: (bool, exit_reason)                      │   │   │
│  │  └──────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                       │
│                        ↓  ↑              ↓  ↑                         │
│                Signals ↓  ↑ Position     ↓  ↑ Risk                   │
│                        ↓  ↑ Checks       ↓  ↑ Validation             │
│                        ↓  ↑              ↓  ↑                         │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  risk_manager.py                                             │   │
│  │  ┌──────────────────────────────────────────────────────┐   │   │
│  │  │  Stop Loss Calculation                               │   │   │
│  │  │  • calculate_stop_loss()                             │   │   │
│  │  │    - ATR-based: entry ± (ATR × mult)                 │   │   │
│  │  │    - Fixed %: entry × (1 ± pct)                      │   │   │
│  │  └──────────────────────────────────────────────────────┘   │   │
│  │                                                               │   │
│  │  ┌──────────────────────────────────────────────────────┐   │   │
│  │  │  Position Sizing                                     │   │   │
│  │  │  • calculate_position_size()                         │   │   │
│  │  │    - Risk-based: (capital × risk%) / risk_per_share  │   │   │
│  │  │    - Max 95% capital utilization                     │   │   │
│  │  └──────────────────────────────────────────────────────┘   │   │
│  │                                                               │   │
│  │  ┌──────────────────────────────────────────────────────┐   │   │
│  │  │  Risk Validation                                     │   │   │
│  │  │  • validate_trade_risk()                             │   │   │
│  │  │    - Stop direction check                            │   │   │
│  │  │    - Risk-reward ratio validation                    │   │   │
│  │  │    - Stop distance validation (0.1% - 10%)           │   │   │
│  │  │  • check_daily_risk_limit()                          │   │   │
│  │  │    - Daily loss limit enforcement                    │   │   │
│  │  └──────────────────────────────────────────────────────┘   │   │
│  │                                                               │   │
│  │  ┌──────────────────────────────────────────────────────┐   │   │
│  │  │  RiskMetrics (Performance Analytics)                 │   │   │
│  │  │  • calculate_max_drawdown()                          │   │   │
│  │  │  • calculate_sharpe_ratio()                          │   │   │
│  │  │  • calculate_sortino_ratio()                         │   │   │
│  │  │  • calculate_calmar_ratio()                          │   │   │
│  │  │  • generate_risk_summary()                           │   │   │
│  │  └──────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                       │
│                              ↓  ↑                                     │
│                    Risk OK   ↓  ↑  Position Info                     │
│                              ↓  ↑                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  positions.py                                                │   │
│  │  ┌──────────────────────────────────────────────────────┐   │   │
│  │  │  Position (data class)                               │   │   │
│  │  │  • Entry/exit tracking                               │   │   │
│  │  │  • P&L calculations                                  │   │   │
│  │  │  • Stop loss checks                                  │   │   │
│  │  │  • Commission & slippage                             │   │   │
│  │  └──────────────────────────────────────────────────────┘   │   │
│  │                                                               │   │
│  │  ┌──────────────────────────────────────────────────────┐   │   │
│  │  │  PositionManager                                     │   │   │
│  │  │  • Track all open/closed positions                   │   │   │
│  │  │  • Risk-based position sizing                        │   │   │
│  │  │  • Daily loss limit enforcement                      │   │   │
│  │  │  • Position limits (per symbol & total)              │   │   │
│  │  │  • P&L tracking & performance metrics                │   │   │
│  │  │  • Commission & slippage accounting                  │   │   │
│  │  └──────────────────────────────────────────────────────┘   │   │
│  │                                                               │   │
│  │  ┌──────────────────────────────────────────────────────┐   │   │
│  │  │  DailyStats                                          │   │   │
│  │  │  • Daily trade aggregation                           │   │   │
│  │  │  • Win rate, profit factor                           │   │   │
│  │  └──────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
                                    │
                                    ↓
┌──────────────────────────────────────────────────────────────────────┐
│                        EXECUTION LAYER (TODO)                         │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  backtest.py (not implemented yet)                           │   │
│  │  • Bar-by-bar simulation                                     │   │
│  │  • Call signal_engine & positions                            │   │
│  │  • Generate equity curve                                     │   │
│  │  • Export results                                            │   │
│  └─────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
                                    │
                                    ↓
┌──────────────────────────────────────────────────────────────────────┐
│                          OUTPUT LAYER                                 │
│  • Trade log CSV                                                      │
│  • Equity curve CSV                                                   │
│  • Performance metrics JSON/CSV                                       │
│  • Visualization plots (optional)                                     │
└──────────────────────────────────────────────────────────────────────┘


═══════════════════════════════════════════════════════════════════════
                            DATA FLOW
═══════════════════════════════════════════════════════════════════════

1. CONFIG LOAD
   config.yaml → load_config() → Config object

2. DATA LOAD
   CSV files → load_data() → pd.DataFrame

3. INDICATOR CALCULATION (per bar or batch)
   Bar/DataFrame → compute_vwap() → VWAP
                → compute_atr() → ATR
                → calculate_z_score() → Z-score
                → calculate_pct_deviation() → % deviation

4. SIGNAL GENERATION
   Bar + Indicators → generate_entry_signal() → "LONG"/"SHORT"/None
   
5. POSITION MANAGEMENT
   Signal → PositionManager.open_position() → Position
   
6. EXIT CHECK
   Position + Bar → check_exit_signal() → (should_exit, reason)
   
7. POSITION CLOSE
   Exit signal → PositionManager.close_position() → Realized P&L
   
8. PERFORMANCE TRACKING
   PositionManager.get_performance_summary() → Metrics


═══════════════════════════════════════════════════════════════════════
                         KEY DESIGN PATTERNS
═══════════════════════════════════════════════════════════════════════

✓ Separation of Concerns
  - Each module has single responsibility
  - Clean interfaces between layers

✓ Dependency Injection
  - Config passed as parameter (not global)
  - PositionManager passed to signal functions

✓ Stateless Functions
  - Signal functions are pure (given same inputs → same outputs)
  - State stored in StrategyState & PositionManager

✓ Type Safety
  - Type hints throughout
  - Dataclasses for structured data

✓ Dual Mode Support
  - Batch mode (DataFrames for backtesting)
  - Incremental mode (Bar-by-bar for live trading)

✓ Configuration Driven
  - All parameters in config.yaml
  - No hardcoded magic numbers
