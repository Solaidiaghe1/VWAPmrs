# Backtest Engine Documentation

## Overview

The **backtest.py** module is the main orchestrator for the VWAP Mean Reversion Strategy. It coordinates all components to simulate historical trading and generate comprehensive performance reports.

## Architecture Flow

```
Data Loading → Indicator Calculation → Signal Generation → Risk Validation 
    → Order Execution → Position Management → Performance Tracking → Results Export
```

## Main Function

### `run_backtest(config, verbose=True)`

Runs a complete backtest for the VWAP mean reversion strategy.

**Parameters:**
- `config` (Config): Configuration object with all strategy parameters
- `verbose` (bool): Print progress messages (default: True)

**Returns:**
Dictionary containing:
- `trades`: DataFrame of all executed trades
- `equity_curve`: DataFrame of equity over time
- `performance`: Dictionary of performance metrics
- `risk_summary`: Risk analysis results
- `execution_summary`: Execution statistics

**Example:**
```python
from src.config import load_config
from src.backtest import run_backtest

config = load_config("config.yaml")
results = run_backtest(config, verbose=True)

print(f"Total P&L: ${results['performance']['total_pnl']:,.2f}")
print(f"Win Rate: {results['performance']['win_rate']:.1%}")
print(f"Sharpe Ratio: {results['performance']['sharpe_ratio']:.2f}")
```

## Processing Loop

### 1. **Symbol Loop**
Iterates through each symbol in `config.symbols`:

```python
for symbol in config.symbols:
    # Load data
    bars = load_bars(symbol, config.data_dir, config.timeframe, config.timestamp_col)
    
    # Initialize state
    state = init_strategy_state(symbol, config)
    
    # Process bars...
```

### 2. **Daily Reset**
At the start of each trading day:
- Resets daily P&L tracking
- Resets VWAP calculation state
- Clears rolling statistics buffers
- Prints previous day's summary

```python
if current_day != bar_date:
    position_manager.reset_daily_tracking(bar.timestamp)
    state = init_strategy_state(symbol, config)
```

### 3. **Bar-by-Bar Processing**

For each bar, the engine:

#### A. **Update Indicators**
```python
vwap = calculate_vwap(bars[:i+1])
state.current_vwap = vwap
update_strategy_state(state, bar, vwap, config)
```

#### B. **Apply Time Filters**
```python
# Skip early bars
if minutes_since_open < session_start + skip_open_minutes:
    continue

# Force close before market close
if minutes_since_open >= session_end - close_before_end_minutes:
    _force_close_positions(...)
    continue
```

#### C. **Exit Logic (if position exists)**

1. **Check Stop Loss**
```python
if position.check_stop_loss(bar.close):
    _close_position(..., reason="stop_loss")
```

2. **Check Max Holding Time**
```python
holding_time = (bar.timestamp - position.entry_time).total_seconds() / 60
if holding_time >= config.max_holding_minutes:
    _close_position(..., reason="max_hold_time")
```

3. **Check Exit Signal**
```python
should_exit, exit_reason = check_exit_condition(
    position, bar, vwap, state.rolling_mean_deviation, 
    state.rolling_std_deviation, config
)
if should_exit:
    _close_position(..., reason=exit_reason)
```

#### D. **Entry Logic (if no position)**

1. **Check Daily Loss Limit**
```python
if not check_daily_risk_limit(position_manager.daily_pnl, config):
    continue
```

2. **Generate Entry Signal**
```python
entry_signal = generate_entry_signal(
    state, bar, vwap, state.rolling_mean_deviation,
    state.rolling_std_deviation, config, position_manager
)
```

3. **Calculate Stop Loss & Position Size**
```python
stop_loss = calculate_stop_loss(bar.close, entry_signal.direction, config, atr)
position_size = calculate_position_size(
    position_manager.current_capital, bar.close, stop_loss, config
)
```

4. **Validate Trade Risk**
```python
is_valid, reason = validate_trade_risk(
    bar.close, stop_loss, entry_signal.direction, config
)
```

5. **Execute Order**
```python
order = Order(symbol, entry_signal.direction, "MARKET", position_size, bar.timestamp)
fill = fill_market_order(order, bar, config)
position = position_manager.open_position(symbol, entry_signal.direction, 
    fill.fill_price, position_size, bar.timestamp, stop_loss, 
    fill.commission, fill.slippage)
```

#### E. **Track Equity**
```python
equity = position_manager.current_capital
for pos in position_manager.open_positions.values():
    equity += pos.calculate_pnl(bar.close)

equity_curve.append({
    'timestamp': bar.timestamp,
    'equity': equity,
    'cash': position_manager.current_capital,
    'open_positions': len(position_manager.open_positions)
})
```

## Results Generation

### Performance Metrics

The backtest calculates comprehensive performance metrics:

**Trading Statistics:**
- Total trades
- Winning trades / Losing trades
- Win rate
- Average win / Average loss
- Profit factor

**Returns:**
- Total P&L
- Gross profit / Gross loss
- Final capital
- Total return %

**Risk Metrics:**
- Maximum drawdown
- Sharpe ratio
- Sortino ratio
- Calmar ratio

**Execution Stats:**
- Total fills
- Average slippage
- Total commission
- Total execution costs

### Output Files

If enabled in config, the backtest saves:

1. **Trades CSV** (`trades_YYYYMMDD_HHMMSS.csv`)
   - All executed trades with entry/exit details
   - P&L per trade
   - Holding time
   - Commission and slippage costs

2. **Equity Curve CSV** (`equity_curve_YYYYMMDD_HHMMSS.csv`)
   - Timestamp
   - Total equity
   - Cash balance
   - Number of open positions
   - Returns

3. **Performance JSON** (`performance_YYYYMMDD_HHMMSS.json`)
   - Complete performance summary
   - Risk metrics
   - Execution summary
   - Configuration snapshot

## Usage Examples

### Basic Backtest

```python
from src.config import load_config
from src.backtest import run_backtest

# Load configuration
config = load_config("config.yaml")

# Run backtest
results = run_backtest(config)
```

### Command Line Usage

```bash
# Verbose output
python -m VWAPmrs.src.backtest config.yaml --verbose

# Quiet mode (no output)
python -m VWAPmrs.src.backtest config.yaml --quiet

# From project root
cd /path/to/VWAPmrs
python -m VWAPmrs.src.backtest ../config.yaml --verbose
```

### Access Results

```python
results = run_backtest(config)

# Performance metrics
print(f"Total Return: {results['performance']['total_return']:.2%}")
print(f"Sharpe Ratio: {results['performance']['sharpe_ratio']:.2f}")
print(f"Max Drawdown: {results['performance']['max_drawdown']:.2%}")

# Trade analysis
trades_df = results['trades']
winning_trades = trades_df[trades_df['pnl'] > 0]
print(f"Average winning trade: ${winning_trades['pnl'].mean():.2f}")

# Equity curve
equity_df = results['equity_curve']
equity_df.plot(x='timestamp', y='equity', title='Equity Curve')
```

### Multiple Backtests (Parameter Sweep)

```python
from src.config import load_config
from src.backtest import run_backtest

base_config = load_config("config.yaml")
entry_thresholds = [1.5, 2.0, 2.5, 3.0]

for threshold in entry_thresholds:
    # Modify config
    base_config.entry_z = threshold
    
    # Run backtest
    results = run_backtest(base_config, verbose=False)
    
    # Collect results
    print(f"Entry Z={threshold}: Return={results['performance']['total_return']:.2%}, "
          f"Sharpe={results['performance']['sharpe_ratio']:.2f}")
```

## Helper Functions

### `_force_close_positions()`
Closes all open positions before market close.

### `_close_position()`
Handles the complete position closing process:
1. Creates close order
2. Executes fill with slippage/commission
3. Updates position manager
4. Records fill

### `_generate_results()`
Compiles all results into a structured dictionary:
- Aggregates performance metrics
- Calculates risk metrics
- Generates summaries

### `_print_results_summary()`
Prints a formatted summary of backtest results to console.

### `_save_results()`
Saves trades, equity curve, and performance to files.

## Configuration Requirements

The backtest requires these configuration parameters:

```yaml
# Core
mode: "backtest"
symbols: ["SPY", "AAPL"]
timeframe: "1min"
initial_capital: 100000

# Signal
signal_type: "zscore"
entry_z: 2.0
exit_z: 0.3
rolling_window: 30

# Risk
max_position_risk_pct: 1.0
daily_loss_limit_pct: 3.0
max_positions_per_symbol: 1
max_total_positions: 10
max_holding_minutes: 180

# Stop Loss
stop_type: "atr"
stop_atr_window: 14
stop_atr_mult: 2.0

# Execution
slippage_model: "bps"
slippage_bps: 5.0
commission_per_trade: 1.0

# Session
session_start: 930    # 09:30
session_end: 1600     # 16:00
skip_open_minutes: 15
close_before_end_minutes: 15

# Data
data_dir: "./data"
timestamp_col: "timestamp"

# Output
results_dir: "./results"
save_trades: true
save_equity_curve: true
```

## Error Handling

The backtest handles various error conditions:

1. **Data Loading Errors**: Skips symbol if data can't be loaded
2. **Daily Loss Limits**: Stops trading for the day if limit hit
3. **Invalid Trades**: Rejects trades that fail validation
4. **Position Limits**: Prevents opening positions beyond limits

## Performance Considerations

- **Memory**: Equity curve stored in memory - long backtests may use significant RAM
- **Speed**: Typical speed ~1000-5000 bars/second (depends on complexity)
- **Optimization**: Consider using fewer symbols or shorter date ranges for testing

## Validation

The test runner (`test_backtest.py`) validates:
1. All imports successful
2. Configuration loads correctly
3. Syntax is valid
4. Data directory exists (warns if not)

Run validation:
```bash
python test_backtest.py
```

## Next Steps

After running a backtest:

1. **Analyze Results**: Review trades CSV and performance metrics
2. **Optimize Parameters**: Test different entry/exit thresholds
3. **Walk-Forward Testing**: Split data into train/test periods
4. **Production**: Move to paper trading with validated parameters

## See Also

- `INTEGRATION_SUMMARY.md` - Full system integration guide
- `ARCHITECTURE.md` - System architecture overview
- `RISK_MANAGER_DOCS.md` - Risk management details
- `EXECUTION_ENGINE_DOCS.md` - Order execution details
