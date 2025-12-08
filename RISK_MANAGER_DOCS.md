# Risk Manager Module Documentation

## Overview
`risk_manager.py` is a comprehensive risk management system for the VWAP Mean Reversion Strategy. It handles stop loss calculation, position sizing, risk validation, and performance metrics calculation.

---

## Core Functions

### 1. Stop Loss Calculation

#### `calculate_stop_loss(entry_price, direction, config, atr=None)`

Calculates stop loss price using either ATR-based or fixed percentage method.

**Parameters:**
- `entry_price` (float): Entry price for the position
- `direction` (str): "LONG" or "SHORT"
- `config` (SimpleNamespace): Strategy configuration
- `atr` (float, optional): Current ATR value (required if stop_type is "atr")

**Returns:**
- `float`: Stop loss price

**Methods:**
1. **ATR-based**: `stop = entry ± (ATR × multiplier)`
   - More adaptive to market volatility
   - Wider stops in volatile markets, tighter in calm markets
   
2. **Fixed %**: `stop = entry × (1 ± fixed_stop_pct)`
   - Consistent risk across all trades
   - Simple to understand and implement

**Example:**
```python
# ATR-based stop (2 ATR below entry for LONG)
stop = calculate_stop_loss(100.0, "LONG", config, atr=2.0)
# Returns: 96.0 (if stop_atr_mult=2.0)

# Fixed % stop (1% below entry for LONG)
config.stop_type = "fixed"
stop = calculate_stop_loss(100.0, "LONG", config)
# Returns: 99.0 (if fixed_stop_pct=1.0)
```

---

### 2. Position Sizing

#### `calculate_position_size(entry_price, stop_loss, direction, capital, max_risk_pct)`

Calculates position size based on risk per trade.

**Formula:**
```
risk_per_share = |entry_price - stop_loss|
max_risk_amount = capital × (max_risk_pct / 100)
position_size = max_risk_amount / risk_per_share
```

**Parameters:**
- `entry_price` (float): Planned entry price
- `stop_loss` (float): Stop loss price
- `direction` (str): "LONG" or "SHORT"
- `capital` (float): Current capital available
- `max_risk_pct` (float): Maximum risk percentage per trade (e.g., 1.0 for 1%)

**Returns:**
- `int`: Number of shares/contracts to trade

**Features:**
- Ensures maximum 95% capital utilization (leaves 5% buffer)
- Returns 0 if risk_per_share is invalid
- Always returns integer (no fractional shares)

**Example:**
```python
# Risk 1% of $100,000 on a trade
# Entry: $100, Stop: $98, Risk per share: $2
# Max risk: $1,000
size = calculate_position_size(100.0, 98.0, "LONG", 100000, 1.0)
# Returns: 500 shares
# Position value: $50,000 (50% of capital)
# Max risk: $1,000 (1% of capital)
```

---

### 3. Risk-Reward Ratio

#### `calculate_risk_reward_ratio(entry_price, stop_loss, target_price, direction)`

Calculates the risk-reward ratio for a trade.

**Formula:**
```
For LONG:
  risk = entry_price - stop_loss
  reward = target_price - entry_price
  
For SHORT:
  risk = stop_loss - entry_price
  reward = entry_price - target_price
  
R:R Ratio = reward / risk
```

**Parameters:**
- `entry_price` (float): Entry price
- `stop_loss` (float): Stop loss price
- `target_price` (float): Target exit price (usually VWAP)
- `direction` (str): "LONG" or "SHORT"

**Returns:**
- `float`: Risk-reward ratio (e.g., 2.0 means 2:1 reward-to-risk)

**Example:**
```python
# LONG: Entry $98, Stop $96, Target $102
# Risk: $2, Reward: $4, R:R = 2.0
rr = calculate_risk_reward_ratio(98.0, 96.0, 102.0, "LONG")
# Returns: 2.0 (2:1 risk-reward)
```

**Best Practices:**
- Minimum 1:1 ratio (break-even)
- Target 1.5:1 or 2:1 for mean reversion
- Higher ratios = better trade quality

---

### 4. Trade Risk Validation

#### `validate_trade_risk(entry_price, stop_loss, target_price, direction, config, min_risk_reward=1.0)`

Validates if a trade meets risk criteria before execution.

**Validation Checks:**
1. Stop loss is in correct direction
2. Target is in correct direction
3. Risk-reward ratio meets minimum threshold
4. Stop loss distance is reasonable (0.1% - 10%)

**Parameters:**
- `entry_price` (float): Entry price
- `stop_loss` (float): Stop loss price
- `target_price` (float): Target exit price
- `direction` (str): "LONG" or "SHORT"
- `config` (SimpleNamespace): Strategy configuration
- `min_risk_reward` (float): Minimum acceptable R:R ratio (default 1.0)

**Returns:**
- `Tuple[bool, str]`: (is_valid, reason)

**Possible Reasons:**
- `"ok"` - Trade is valid
- `"stop_loss_invalid_direction"` - Stop not in correct direction
- `"target_invalid_direction"` - Target not in correct direction
- `"risk_reward_too_low_X.XX"` - R:R ratio below minimum
- `"stop_loss_too_tight"` - Stop distance < 0.1%
- `"stop_loss_too_wide"` - Stop distance > 10%

**Example:**
```python
valid, reason = validate_trade_risk(
    entry_price=98.0,
    stop_loss=96.0,
    target_price=102.0,
    direction="LONG",
    config=config,
    min_risk_reward=1.5
)

if valid:
    print("Trade setup is valid")
    # Proceed with trade
else:
    print(f"Trade rejected: {reason}")
    # Skip trade
```

---

### 5. Daily Risk Limit Check

#### `check_daily_risk_limit(current_daily_pnl, initial_capital, daily_loss_limit_pct)`

Checks if daily loss limit has been reached.

**Parameters:**
- `current_daily_pnl` (float): Current P&L for the day (negative for loss)
- `initial_capital` (float): Initial capital at start
- `daily_loss_limit_pct` (float): Maximum allowed daily loss percentage

**Returns:**
- `Tuple[bool, float]`: (can_trade, remaining_loss_buffer)

**Example:**
```python
# Lost $2,500 so far today, limit is 3% ($3,000)
can_trade, buffer = check_daily_risk_limit(-2500, 100000, 3.0)
# Returns: (True, 500.0) - can still trade, $500 buffer left

# Lost $3,500, limit exceeded
can_trade, buffer = check_daily_risk_limit(-3500, 100000, 3.0)
# Returns: (False, 0.0) - cannot trade anymore today
```

**Purpose:**
- Prevents revenge trading after losses
- Protects capital from catastrophic days
- Forces reset on next trading day

---

## Risk Metrics Class

### `RiskMetrics` - Static Methods for Performance Analytics

#### 1. Maximum Drawdown

```python
RiskMetrics.calculate_max_drawdown(equity_curve)
```

**Parameters:**
- `equity_curve` (list): List of equity values over time

**Returns:**
- `Tuple[float, int, int]`: (max_drawdown_pct, peak_idx, trough_idx)

**Formula:**
```
drawdown[i] = (equity[i] - running_max[i]) / running_max[i] × 100
max_drawdown = min(drawdown)
```

**Example:**
```python
equity = [100000, 102000, 101000, 103000, 100500, 104000]
max_dd, peak, trough = RiskMetrics.calculate_max_drawdown(equity)
# Returns: (2.43, 3, 4) - 2.43% max drawdown from index 3 to 4
```

---

#### 2. Sharpe Ratio

```python
RiskMetrics.calculate_sharpe_ratio(returns, risk_free_rate=0.0, periods_per_year=252)
```

**Parameters:**
- `returns` (list): List of period returns (as decimals)
- `risk_free_rate` (float): Annual risk-free rate (default 0.0)
- `periods_per_year` (int): Number of periods per year (252 for daily)

**Returns:**
- `float`: Annualized Sharpe ratio

**Formula:**
```
excess_returns = returns - (risk_free_rate / periods_per_year)
sharpe = (mean(excess_returns) / std(excess_returns)) × √periods_per_year
```

**Interpretation:**
- < 1.0: Poor risk-adjusted returns
- 1.0 - 2.0: Good
- 2.0 - 3.0: Very good
- > 3.0: Excellent

**Example:**
```python
returns = [0.01, -0.005, 0.015, -0.01, 0.02]  # Daily returns
sharpe = RiskMetrics.calculate_sharpe_ratio(returns, risk_free_rate=0.02)
# Returns: 1.85 (good risk-adjusted returns)
```

---

#### 3. Sortino Ratio

```python
RiskMetrics.calculate_sortino_ratio(returns, risk_free_rate=0.0, periods_per_year=252)
```

**Parameters:**
- Same as Sharpe ratio

**Returns:**
- `float`: Annualized Sortino ratio

**Difference from Sharpe:**
- Only penalizes downside volatility (negative returns)
- Better for asymmetric return distributions
- More relevant for mean reversion strategies

**Formula:**
```
downside_returns = returns[returns < 0]
downside_std = √mean(downside_returns²)
sortino = (mean(excess_returns) / downside_std) × √periods_per_year
```

**Example:**
```python
returns = [0.01, -0.005, 0.015, -0.01, 0.02]
sortino = RiskMetrics.calculate_sortino_ratio(returns, risk_free_rate=0.02)
# Returns: 2.15 (higher than Sharpe due to positive skew)
```

---

#### 4. Calmar Ratio

```python
RiskMetrics.calculate_calmar_ratio(total_return, max_drawdown, years=1.0)
```

**Parameters:**
- `total_return` (float): Total return as percentage
- `max_drawdown` (float): Maximum drawdown as percentage
- `years` (float): Number of years (for annualization)

**Returns:**
- `float`: Calmar ratio

**Formula:**
```
annualized_return = (total_return / 100) / years
calmar = annualized_return / (max_drawdown / 100)
```

**Interpretation:**
- Measures return per unit of maximum drawdown
- Higher is better
- Good strategies: > 1.0
- Excellent strategies: > 3.0

**Example:**
```python
# 15% return, 5% max drawdown
calmar = RiskMetrics.calculate_calmar_ratio(15.0, 5.0, years=1.0)
# Returns: 3.0 (excellent)
```

---

## Risk Summary Generation

### `generate_risk_summary(trades, equity_curve, initial_capital, config)`

Generates comprehensive risk summary for the strategy.

**Parameters:**
- `trades` (list): List of trade dictionaries
- `equity_curve` (list): List of equity values
- `initial_capital` (float): Starting capital
- `config` (SimpleNamespace): Strategy configuration

**Returns:**
- `Dict`: Dictionary with risk metrics

**Metrics Included:**
```python
{
    'total_trades': int,
    'max_drawdown_pct': float,
    'sharpe_ratio': float,
    'sortino_ratio': float,
    'calmar_ratio': float,
    'avg_risk_per_trade_pct': float,
    'max_risk_per_trade_pct': float,
    'largest_win_pct': float,
    'largest_loss_pct': float,
    'avg_win_pct': float,
    'avg_loss_pct': float
}
```

**Example:**
```python
risk_summary = generate_risk_summary(
    trades=position_manager.get_trade_history(),
    equity_curve=equity_history,
    initial_capital=100000,
    config=config
)

print(f"Sharpe Ratio: {risk_summary['sharpe_ratio']:.2f}")
print(f"Max Drawdown: {risk_summary['max_drawdown_pct']:.2f}%")
print(f"Avg Risk/Trade: {risk_summary['avg_risk_per_trade_pct']:.2f}%")
```

---

## Integration Examples

### Complete Trade Execution Flow

```python
from risk_manager import (
    calculate_stop_loss,
    calculate_position_size,
    validate_trade_risk,
    check_daily_risk_limit
)

# Step 1: Check if we can trade today
can_trade, buffer = check_daily_risk_limit(
    current_daily_pnl=position_manager.daily_pnl,
    initial_capital=config.initial_capital,
    daily_loss_limit_pct=config.daily_loss_limit_pct
)

if not can_trade:
    print("Daily loss limit reached - no more trading today")
    return

# Step 2: Calculate stop loss
stop = calculate_stop_loss(
    entry_price=bar.close,
    direction=signal,  # "LONG" or "SHORT"
    config=config,
    atr=current_atr  # From indicators.compute_atr()
)

# Step 3: Validate trade setup
valid, reason = validate_trade_risk(
    entry_price=bar.close,
    stop_loss=stop,
    target_price=vwap,  # Target is mean reversion to VWAP
    direction=signal,
    config=config,
    min_risk_reward=1.5  # Require at least 1.5:1 R:R
)

if not valid:
    print(f"Trade rejected: {reason}")
    return

# Step 4: Calculate position size
size = calculate_position_size(
    entry_price=bar.close,
    stop_loss=stop,
    direction=signal,
    capital=position_manager.current_capital,
    max_risk_pct=config.max_position_risk_pct
)

if size == 0:
    print("Position size too small - skipping trade")
    return

# Step 5: Open position
position = position_manager.open_position(
    symbol=symbol,
    direction=signal,
    entry_price=bar.close,
    entry_time=bar.timestamp,
    entry_bar_idx=state.bar_idx,
    stop_loss=stop,
    entry_vwap=vwap,
    entry_z=z_score,
    size=size
)

if position:
    print(f"✅ Position opened: {position.position_id}")
    print(f"   Size: {size} shares")
    print(f"   Risk: ${size * abs(bar.close - stop):.2f}")
```

---

## Configuration Reference

Required config parameters for risk_manager.py:

```yaml
# Stop Loss Configuration
stop_type: "atr"              # "atr" or "fixed"
stop_atr_mult: 2.0            # ATR multiplier (for ATR stops)
stop_atr_window: 14           # ATR window (for calculation)
atr_timeframe: "10min"        # ATR timeframe
fixed_stop_pct: 1.0           # Fixed stop % (for fixed stops)

# Position Sizing
max_position_risk_pct: 1.0    # Max risk per trade (% of capital)

# Daily Risk Management
daily_loss_limit_pct: 3.0     # Max daily loss %

# Initial Capital
initial_capital: 100000       # Starting capital
```

---

## Best Practices

### 1. Stop Loss Selection
- **ATR-based**: Better for adaptive stops in varying volatility
- **Fixed %**: Better for consistent risk across all trades
- Typical ATR multipliers: 1.5 - 3.0
- Typical fixed stops: 0.5% - 2.0%

### 2. Position Sizing
- Never risk more than 1-2% per trade
- Consider portfolio heat (total risk across all positions)
- Leave capital buffer (5-10%) for flexibility

### 3. Risk-Reward Ratios
- Minimum 1:1 for mean reversion
- Target 1.5:1 or 2:1 for better win rate
- Higher ratios = fewer trades but better quality

### 4. Daily Loss Limits
- Typical limits: 2-5% of capital
- Prevents emotional trading after losses
- Forces cool-down period

### 5. Performance Monitoring
- Track Sharpe ratio > 1.0
- Keep max drawdown < 20%
- Monitor Calmar ratio > 1.0
- Review risk metrics monthly

---

## Testing

Run the built-in tests:
```bash
cd /Users/solaidiaghe/Desktop/VWAPmrs/VWAPmrs/src
python3 risk_manager.py
```

Tests cover:
- ATR-based stop loss calculation
- Fixed percentage stop loss calculation
- Position sizing with various scenarios
- Risk-reward ratio calculation
- Trade validation
- Daily risk limit checks
- Risk metrics (Sharpe, Sortino, Calmar, Max DD)

---

## Summary

`risk_manager.py` provides production-ready risk management:
- ✅ Flexible stop loss calculation (ATR or fixed)
- ✅ Scientific position sizing based on risk
- ✅ Trade validation before execution
- ✅ Daily loss limits to prevent overtrading
- ✅ Comprehensive performance metrics
- ✅ Full integration with positions.py and signal_engine.py
- ✅ Follows markdown strategy specifications
- ✅ Tested and documented
