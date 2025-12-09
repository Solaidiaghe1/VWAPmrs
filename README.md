# VWAPmrs - VWAP Mean Reversion Strategy

A comprehensive backtesting engine for VWAP (Volume-Weighted Average Price) mean reversion trading strategies.

## Overview

VWAPmrs is a modular backtesting system that simulates intraday trading strategies based on VWAP deviation signals. It includes complete risk management, position tracking, execution simulation, and performance analytics.

## Quick Start

### 1. Installation

```bash
# Install dependencies
pip install -r requirements.txt
```

### 2. Generate Sample Data

```bash
# Generate sample 1-minute bar data for testing
python generate_sample_data.py
```

This creates sample data files in the `data/` directory:
- `SPY_1min.csv`
- `AAPL_1min.csv`
- `MSFT_1min.csv`

### 3. Run a Backtest

```bash
# Run backtest with verbose output
python -m VWAPmrs.src.backtest config.yaml --verbose

# Run backtest in quiet mode
python -m VWAPmrs.src.backtest config.yaml --quiet
```

## Running Different Components

### Backtest Engine (Main)

**Basic Usage:**
```bash
python -m VWAPmrs.src.backtest config.yaml --verbose
```

**From Python:**
```python
from VWAPmrs.src.config import load_config
from VWAPmrs.src.backtest import run_backtest

# Load configuration
config = load_config("config.yaml")

# Run backtest
results = run_backtest(config, verbose=True)

# Access results
print(f"Total Return: {results['performance']['total_return']:.2%}")
print(f"Sharpe Ratio: {results['performance']['sharpe_ratio']:.2f}")
print(f"Max Drawdown: {results['performance']['max_drawdown']:.2%}")
```

### Test/Validation

```bash
# Validate backtest setup
python3 test_backtest.py
```

### Parameter Optimization

Run multiple backtests with different parameters:

```python
from VWAPmrs.src.config import load_config
from VWAPmrs.src.backtest import run_backtest

base_config = load_config("config.yaml")

# Test different entry thresholds
for entry_z in [1.5, 2.0, 2.5, 3.0]:
    base_config.entry_z = entry_z
    results = run_backtest(base_config, verbose=False)
    print(f"Entry Z={entry_z}: Return={results['performance']['total_return']:.2%}")
```

### Analyze Results

```python
import pandas as pd

# Load saved results
trades = pd.read_csv('results/trades_YYYYMMDD_HHMMSS.csv')
equity = pd.read_csv('results/equity_curve_YYYYMMDD_HHMMSS.csv')

# Analyze trades
winning_trades = trades[trades['pnl'] > 0]
print(f"Win Rate: {len(winning_trades) / len(trades):.1%}")
print(f"Avg Win: ${winning_trades['pnl'].mean():.2f}")

# Plot equity curve
import matplotlib.pyplot as plt
plt.figure(figsize=(12, 6))
plt.plot(pd.to_datetime(equity['timestamp']), equity['equity'])
plt.title('Equity Curve')
plt.xlabel('Time')
plt.ylabel('Equity ($)')
plt.show()
```

## Configuration

Edit `config.yaml` to customize strategy parameters:

```yaml
# Core Settings
mode: "backtest"
symbols: ["SPY", "AAPL"]
timeframe: "1min"
initial_capital: 100000

# Signal Parameters
signal_type: "zscore"
entry_z: 2.0        # Z-score threshold for entry
exit_z: 0.3         # Z-score threshold for exit
rolling_window: 30  # Bars for rolling statistics

# Risk Management
max_position_risk_pct: 1.0      # Max 1% risk per trade
daily_loss_limit_pct: 3.0       # Stop trading if -3% daily loss
max_holding_minutes: 180        # Max 3-hour hold time

# Stop Loss
stop_type: "atr"
stop_atr_mult: 2.0

# Execution
slippage_bps: 5.0              # 5 basis points slippage
commission_per_trade: 1.0      # $1 per trade

# Session Times
session_start: 930             # 09:30 AM
session_end: 1600              # 04:00 PM
skip_open_minutes: 15          # Skip first 15 minutes
close_before_end_minutes: 15   # Close positions 15 min before close

# Output
results_dir: "./results"
save_trades: true
save_equity_curve: true
```

## Output Files

After running a backtest, results are saved to the `results/` directory:

1. **trades_YYYYMMDD_HHMMSS.csv** - All executed trades with P&L
2. **equity_curve_YYYYMMDD_HHMMSS.csv** - Equity over time
3. **performance_YYYYMMDD_HHMMSS.json** - Performance metrics and risk analysis

## Project Structure

```
VWAPmrs/
├── src/
│   ├── backtest.py         # Main backtest orchestrator
│   ├── config.py           # Configuration management
│   ├── data_loader.py      # Data loading utilities
│   ├── execution_engine.py # Order execution simulation
│   ├── indicators.py       # VWAP and indicator calculations
│   ├── positions.py        # Position management
│   ├── risk_manager.py     # Risk validation and checks
│   └── signal_engine.py    # Entry/exit signal generation
├── config.yaml             # Strategy configuration
├── generate_sample_data.py # Sample data generator
└── test_backtest.py        # Validation tests
```

## Key Features

- **Modular Architecture**: Clean separation of concerns (data, signals, risk, execution)
- **Comprehensive Risk Management**: Position sizing, stop losses, daily limits
- **Realistic Execution**: Slippage and commission modeling
- **Performance Analytics**: Sharpe ratio, max drawdown, win rate, profit factor
- **Flexible Configuration**: YAML-based parameter management
- **Multiple Symbols**: Trade multiple instruments simultaneously
- **Session Management**: Market hours, warm-up periods, early close

## Documentation

Detailed documentation for each component:

- **[BACKTEST_ENGINE_DOCS.md](BACKTEST_ENGINE_DOCS.md)** - Main backtest engine
- **[INTEGRATION_SUMMARY.md](INTEGRATION_SUMMARY.md)** - System integration guide
- **[RISK_MANAGER_DOCS.md](RISK_MANAGER_DOCS.md)** - Risk management details
- **[EXECUTION_ENGINE_DOCS.md](EXECUTION_ENGINE_DOCS.md)** - Order execution
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - System architecture
- **[VWAP_Mean_Reversion_Strategy.md](VWAP_Mean_Reversion_Strategy.md)** - Strategy details

## Common Tasks

### Change Symbols to Trade

Edit `config.yaml`:
```yaml
symbols: ["QQQ", "TSLA", "NVDA"]
```

### Adjust Entry Sensitivity

More aggressive (more trades):
```yaml
entry_z: 1.5
```

More conservative (fewer trades):
```yaml
entry_z: 3.0
```

### Modify Risk Per Trade

```yaml
max_position_risk_pct: 0.5  # 0.5% risk per trade
```

### Change Trading Hours

```yaml
session_start: 1000          # Start at 10:00 AM
session_end: 1530            # End at 3:30 PM
```

## Troubleshooting

### "No module named 'VWAPmrs'"

Make sure you're running from the parent directory:
```bash
cd /Users/solaidiaghe/Desktop/VWAPmrs
python -m VWAPmrs.src.backtest config.yaml
```

### "Data file not found"

Generate sample data first:
```bash
python generate_sample_data.py
```

Or ensure your data files are in the correct format with columns:
- `timestamp` (datetime)
- `open`, `high`, `low`, `close` (float)
- `volume` (int)

### No trades generated

- Check if entry threshold is too strict (try lower `entry_z`)
- Verify data covers trading hours specified in config
- Check daily loss limit hasn't been hit

## Performance Tips

- Start with a single symbol for testing
- Use shorter date ranges during parameter optimization
- Disable verbose output for multiple backtests
- Consider memory usage for very long backtests

## Next Steps

1. **Run basic backtest** with default parameters
2. **Review results** in the `results/` directory
3. **Optimize parameters** using parameter sweep
4. **Validate on different time periods** (walk-forward testing)
5. **Paper trade** with validated parameters before going live

## License

[Add your license here]

## Contributing

[Add contribution guidelines here]

## other linees
python3 -m VWAPmrs.src.backtest config.yaml --verbose 2>&1 | grep -A 30 "PERFORMANCE SUMMARY"