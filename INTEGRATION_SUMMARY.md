# Integration Summary: positions.py & signal_engine.py

## Overview
Successfully implemented `positions.py` and integrated it with `signal_engine.py` for the VWAP Mean Reversion Strategy.

---

## New Module: `positions.py`

### Classes Implemented

#### 1. **`Position`** (Enhanced)
Represents an open or closed trading position with complete lifecycle tracking.

**Key Features:**
- Entry/exit tracking (price, time, bar index)
- P&L calculations (unrealized & realized)
- Stop loss hit detection
- Commission & slippage accounting
- Dictionary export for logging/analysis

**Methods:**
- `unrealized_pnl(current_price)` - Calculate open P&L
- `is_stop_loss_hit(bar)` - Check if stop triggered
- `holding_minutes(current_time)` - Time held
- `close_position(...)` - Close and calculate realized P&L
- `to_dict()` - Export to dictionary

---

#### 2. **`DailyStats`**
Tracks daily performance statistics.

**Metrics Tracked:**
- Trade counts (total, winning, losing)
- P&L aggregation (total, gross profit/loss)
- Commission & slippage costs
- Win rate calculation
- Profit factor calculation

---

#### 3. **`PositionManager`** (Core Position Management)
Central system for managing all positions and risk controls.

**Responsibilities:**
- Position tracking (open & closed, per symbol)
- Position sizing (risk-based calculation)
- Risk management (daily loss limits, position limits)
- P&L tracking (realized/unrealized, daily/cumulative)
- Performance metrics & reporting

**Key Methods:**

##### Position Management
- `open_position(...)` - Open new position with auto-sizing
- `close_position(...)` - Close position and update tracking
- `get_position(symbol)` - Get open position for symbol
- `get_all_positions(symbol=None)` - Get all open positions

##### Risk Control
- `can_open_position(symbol)` - Check if position can be opened
  - Daily loss limit check
  - Max total positions check
  - Max positions per symbol check
- `calculate_position_size(...)` - Risk-based sizing
  - Uses `config.max_position_risk_pct`
  - Accounts for stop loss distance
  - Ensures sufficient capital

##### Tracking & Reporting
- `reset_daily_tracking(date)` - Reset for new trading day
- `get_total_unrealized_pnl(prices)` - Calculate open P&L
- `get_performance_summary()` - Complete performance metrics
- `get_trade_history()` - Export all trades

**Performance Metrics:**
- Total trades, win/loss counts, win rate
- Total P&L, gross profit/loss, profit factor
- Average win/loss, average trade
- Commission & slippage costs
- Current capital & total return %

---

## Updated Module: `signal_engine.py`

### Changes Made

#### 1. **Removed Duplicate `Position` Class**
- Now imports from `positions.py`
- Eliminates code duplication
- Single source of truth

#### 2. **Updated `StrategyState` Class**
**Removed:**
- `current_position` field (now managed by PositionManager)
- `daily_pnl` field (now in PositionManager)
- `trades_today` field (now in PositionManager.daily_stats)

**Retained:**
- VWAP state tracking
- Rolling statistics
- Bar indexing
- Session timing

#### 3. **Updated `generate_entry_signal()` Function**
**New Parameter:**
- `position_manager: PositionManager` - Required for position checks

**Changed Logic:**
```python
# OLD: Check via state.current_position
if state.current_position is not None:
    return None

# NEW: Check via PositionManager
if position_manager.get_position(state.symbol) is not None:
    return None
```

#### 4. **Exit Signal Logic (`check_exit_signal`)**
- Unchanged - still works with Position objects
- Compatible with both old and new Position class
- Works seamlessly with PositionManager

---

## Integration Benefits

### 1. **Separation of Concerns**
- **`signal_engine.py`**: Signal generation logic only
- **`positions.py`**: Position management, risk, and tracking
- Clean, modular design

### 2. **Enhanced Risk Management**
- Daily loss limits enforced automatically
- Position limits (per symbol & total)
- Risk-based position sizing
- Commission & slippage tracking

### 3. **Better Performance Tracking**
- Daily statistics aggregation
- Complete trade history
- Performance metrics (win rate, profit factor, etc.)
- Capital tracking

### 4. **Scalability**
- Multi-symbol support
- Multiple positions per symbol (configurable)
- Supports portfolio-level risk management

### 5. **Production Ready**
- Comprehensive error checking
- Type hints throughout
- Detailed docstrings
- Test code included

---

## Usage Example

```python
from config import load_config
from positions import PositionManager
from signal_engine import generate_entry_signal, check_exit_signal, StrategyState
from indicators import Bar

# Load configuration
config = load_config("config.yaml")

# Initialize PositionManager
pm = PositionManager(config=config, initial_capital=config.initial_capital)
pm.reset_daily_tracking(datetime.now())

# Create strategy state for symbol
state = StrategyState(
    symbol="SPY",
    session_start=datetime(2025, 1, 2, 9, 30),
    session_end=datetime(2025, 1, 2, 16, 0)
)

# For each bar:
bar = Bar(...)  # Current bar data
vwap = ...      # Calculated VWAP
z_score = ...   # Calculated z-score

# Generate entry signal
signal = generate_entry_signal(
    bar=bar,
    vwap=vwap,
    z_score=z_score,
    pct_deviation=pct_deviation,
    config=config,
    state=state,
    position_manager=pm  # <-- New parameter
)

# If signal, open position
if signal:
    position = pm.open_position(
        symbol=state.symbol,
        direction=signal,
        entry_price=bar.close,
        entry_time=bar.timestamp,
        entry_bar_idx=state.bar_idx,
        stop_loss=calculated_stop,
        entry_vwap=vwap,
        entry_z=z_score
    )

# Check exit for open positions
position = pm.get_position(state.symbol)
if position:
    should_exit, exit_reason = check_exit_signal(
        position=position,
        bar=bar,
        z_score=z_score,
        pct_deviation=pct_deviation,
        config=config,
        state=state
    )
    
    if should_exit:
        pnl = pm.close_position(
            position=position,
            exit_price=bar.close,
            exit_time=bar.timestamp,
            exit_reason=exit_reason
        )
        state.last_exit_bar_idx = state.bar_idx

# Get performance summary
summary = pm.get_performance_summary()
print(f"Total P&L: ${summary['total_pnl']:.2f}")
print(f"Win Rate: {summary['win_rate']:.1f}%")
```

---

## Configuration Requirements

The following config parameters are required for `PositionManager`:

```yaml
# Risk Management
max_position_risk_pct: 1.0          # % of capital to risk per trade
daily_loss_limit_pct: 3.0           # Max daily loss %
max_positions_per_symbol: 1         # Max positions per symbol
max_total_positions: 5              # Max total positions

# Costs
commission_per_trade: 1.0           # Commission per trade ($)
slippage_bps: 5.0                   # Slippage in basis points
slippage_model: "bps"               # "bps" or "volume"

# Capital
initial_capital: 100000             # Starting capital
```

---

## Next Steps

1. **Implement Backtest Engine** - Use PositionManager in backtesting loop
2. **Add Stop Loss Calculation** - Implement ATR-based & fixed stop logic
3. **Create Results Export** - Export trades and equity curve
4. **Add Logging** - Log position entries/exits for debugging
5. **Testing** - Comprehensive unit tests for PositionManager
6. **Documentation** - Update README with usage examples

---

## File Status

✅ **`positions.py`** - Complete and tested (structure)
✅ **`signal_engine.py`** - Updated and integrated
✅ **`risk_manager.py`** - Complete with stop loss, position sizing, and risk metrics
✅ **`execution_engine.py`** - Complete with order fills, slippage, and commission
⏳ **`backtest.py`** - Not yet implemented
✅ **`config.py`** - Complete
✅ **`indicators.py`** - Complete
✅ **`data_loader.py`** - Complete

---

## New Module: `risk_manager.py`

### Overview
Comprehensive risk management system handling stop loss calculation, position sizing, risk validation, and performance metrics.

### Key Functions

#### Stop Loss Calculation
```python
calculate_stop_loss(entry_price, direction, config, atr=None)
```
- **ATR-based**: `stop = entry ± (ATR × multiplier)`
- **Fixed %**: `stop = entry × (1 ± stop_pct)`
- Supports both LONG and SHORT positions

#### Position Sizing
```python
calculate_position_size(entry_price, stop_loss, direction, capital, max_risk_pct)
```
- Risk-based sizing: `size = (capital × risk_pct) / risk_per_share`
- Ensures maximum 95% capital utilization
- Returns integer share count

#### Risk-Reward Ratio
```python
calculate_risk_reward_ratio(entry_price, stop_loss, target_price, direction)
```
- Calculates R:R ratio for trade validation
- Used to filter low-quality setups

#### Trade Validation
```python
validate_trade_risk(entry_price, stop_loss, target_price, direction, config, min_risk_reward)
```
- Validates stop loss direction
- Checks minimum R:R ratio
- Ensures stop distance is reasonable (0.1% - 10%)
- Returns: `(is_valid: bool, reason: str)`

#### Daily Risk Limit
```python
check_daily_risk_limit(current_daily_pnl, initial_capital, daily_loss_limit_pct)
```
- Checks if daily loss limit reached
- Returns remaining risk buffer
- Prevents overtrading after losses

### Risk Metrics Class

#### `RiskMetrics` - Performance Analytics

**Maximum Drawdown**
```python
RiskMetrics.calculate_max_drawdown(equity_curve)
```
- Returns: `(max_drawdown_pct, peak_idx, trough_idx)`

**Sharpe Ratio**
```python
RiskMetrics.calculate_sharpe_ratio(returns, risk_free_rate, periods_per_year)
```
- Annualized risk-adjusted returns
- Default: 252 periods (daily)

**Sortino Ratio**
```python
RiskMetrics.calculate_sortino_ratio(returns, risk_free_rate, periods_per_year)
```
- Uses downside deviation only
- Better measure for asymmetric strategies

**Calmar Ratio**
```python
RiskMetrics.calculate_calmar_ratio(total_return, max_drawdown, years)
```
- Return / Max Drawdown
- Measures return per unit of risk

### Risk Summary Generation
```python
generate_risk_summary(trades, equity_curve, initial_capital, config)
```

**Returns comprehensive metrics:**
- Maximum drawdown %
- Sharpe, Sortino, Calmar ratios
- Average & max risk per trade
- Largest win/loss percentages
- Average win/loss percentages

### Integration with Existing Modules

#### With `positions.py`
```python
from risk_manager import calculate_stop_loss, calculate_position_size

# Calculate stop loss
stop = calculate_stop_loss(entry_price, direction, config, atr=current_atr)

# Calculate position size
size = calculate_position_size(entry_price, stop, direction, capital, config.max_position_risk_pct)

# Open position with calculated values
position = position_manager.open_position(
    symbol=symbol,
    direction=direction,
    entry_price=entry_price,
    stop_loss=stop,
    size=size,
    # ... other params
)
```

#### With `signal_engine.py`
```python
from risk_manager import validate_trade_risk

# Before opening position, validate risk
valid, reason = validate_trade_risk(
    entry_price=bar.close,
    stop_loss=calculated_stop,
    target_price=vwap,
    direction=signal,
    config=config,
    min_risk_reward=1.5
)

if valid:
    # Proceed with trade
else:
    print(f"Trade rejected: {reason}")
```

### Configuration Requirements

```yaml
# Stop Loss Configuration
stop_type: "atr"              # "atr" or "fixed"
stop_atr_mult: 2.0            # ATR multiplier (if using ATR stops)
stop_atr_window: 14           # ATR calculation window
atr_timeframe: "10min"        # ATR timeframe
fixed_stop_pct: 1.0           # Fixed stop % (if using fixed stops)

# Position Sizing
max_position_risk_pct: 1.0    # Max risk per trade (% of capital)

# Daily Risk Limits
daily_loss_limit_pct: 3.0     # Max daily loss %
```

### Usage Example

```python
from risk_manager import (
    calculate_stop_loss,
    calculate_position_size,
    validate_trade_risk,
    check_daily_risk_limit,
    generate_risk_summary
)

# 1. Calculate stop loss
stop = calculate_stop_loss(
    entry_price=100.0,
    direction="LONG",
    config=config,
    atr=2.0  # Only needed if stop_type="atr"
)

# 2. Validate trade setup
valid, reason = validate_trade_risk(
    entry_price=100.0,
    stop_loss=stop,
    target_price=vwap,  # Target is VWAP
    direction="LONG",
    config=config,
    min_risk_reward=1.5
)

if not valid:
    print(f"Trade rejected: {reason}")
    return

# 3. Check daily risk limit
can_trade, buffer = check_daily_risk_limit(
    current_daily_pnl=position_manager.daily_pnl,
    initial_capital=config.initial_capital,
    daily_loss_limit_pct=config.daily_loss_limit_pct
)

if not can_trade:
    print("Daily loss limit reached")
    return

# 4. Calculate position size
size = calculate_position_size(
    entry_price=100.0,
    stop_loss=stop,
    direction="LONG",
    capital=position_manager.current_capital,
    max_risk_pct=config.max_position_risk_pct
)

# 5. Open position
position = position_manager.open_position(
    symbol="SPY",
    direction="LONG",
    entry_price=100.0,
    stop_loss=stop,
    size=size,
    # ...
)

# 6. At end of backtest, generate risk summary
risk_summary = generate_risk_summary(
    trades=position_manager.get_trade_history(),
    equity_curve=equity_history,
    initial_capital=config.initial_capital,
    config=config
)

print(f"Sharpe Ratio: {risk_summary['sharpe_ratio']:.2f}")
print(f"Max Drawdown: {risk_summary['max_drawdown_pct']:.2f}%")
```

---

## New Module: `execution_engine.py`

### Overview
Production-ready order execution simulator for market order fills, slippage calculation, commission application, and position updates. Used by backtesting, paper trading, and adaptable for live broker integration.

### Key Data Structures

#### `Order` (Dataclass)
Represents a trading order to be filled.
```python
Order(
    symbol: str,
    direction: str,        # "LONG" or "SHORT"
    order_type: str,       # "MARKET", "LIMIT", "STOP"
    size: int,
    timestamp: datetime,
    limit_price: Optional[float] = None,
    stop_price: Optional[float] = None
)
```

#### `Fill` (Dataclass)
Represents an executed order with all costs.
```python
Fill(
    order: Order,
    fill_price: float,
    fill_time: datetime,
    slippage: float,       # $ cost
    commission: float,     # $ cost
    fill_size: int
)
```

**Properties:**
- `total_cost` - Total cost including slippage and commission
- `effective_price` - Price per share including all costs

### Core Functions

#### 1. fill_market_order()
Execute a market order and return fill details.

**Modes:**
- **Realistic** (`use_realistic_fills=True`): Uses close price + slippage
- **Optimistic** (`use_realistic_fills=False`): Uses open price + slippage

```python
fill = fill_market_order(order, bar, config, use_realistic_fills=True)
```

#### 2. simulate_fill_price()
Simulate realistic fill price with slippage.

**Slippage Models:**

**A. BPS (Basis Points)**
```python
config.slippage_model = "bps"
config.slippage_bps = 5.0  # 0.05%

# LONG: pay more
fill_price = base_price × (1 + bps/10000)

# SHORT: receive less
fill_price = base_price × (1 - bps/10000)
```

**B. Volume-Based**
```python
config.slippage_model = "volume"
config.volume_participation_limit_pct = 10.0

participation_pct = (order.size / bar.volume) × 100

if participation_pct > limit:
    # Increase slippage proportionally
    slippage_multiplier = 1 + (participation_pct / limit_pct)
```

#### 3. apply_slippage()
Calculate slippage cost in dollars.
```python
slippage_cost = |fill_price - base_price| × order.size
```

#### 4. apply_commission()
Calculate commission cost for the order.
```python
commission = config.commission_per_trade
```

#### 5. update_position_from_fill()
Create position update data after a fill.

**Opening Position:**
```python
update_data = update_position_from_fill(fill)
# Returns: {'action': 'open', 'entry_price': ..., 'size': ...}
```

**Closing Position:**
```python
close_data = update_position_from_fill(exit_fill, position)
# Returns: {'action': 'close', 'exit_price': ..., 'net_pnl': ...}
```

#### 6. validate_order()
Validate if order can be executed.

**Checks:**
- Order size > 0
- Sufficient volume (if enabled)
- Price within bar range (for limit orders)

```python
valid, reason = validate_order(order, bar, config)
if not valid:
    print(f"Order rejected: {reason}")
```

#### 7. generate_execution_summary()
Generate summary statistics for executed orders.

```python
summary = generate_execution_summary(fills)
# Returns:
{
    'total_fills': int,
    'total_shares': int,
    'total_slippage': float,
    'total_commission': float,
    'avg_slippage_per_fill': float,
    'avg_slippage_bps': float
}
```

### Integration with Backtesting

```python
from execution_engine import fill_market_order, validate_order, Order

# In backtest loop
for bar in bars:
    # Generate signal
    signal = generate_entry_signal(...)
    
    if signal:
        # Create order
        order = Order(
            symbol=symbol,
            direction=signal,
            order_type="MARKET",
            size=calculated_size,
            timestamp=bar.timestamp
        )
        
        # Validate
        valid, reason = validate_order(order, bar, config)
        if not valid:
            continue
        
        # Fill order
        fill = fill_market_order(order, bar, config, use_realistic_fills=True)
        
        # Update position
        update_data = update_position_from_fill(fill)
        position = position_manager.open_position(
            symbol=update_data['symbol'],
            entry_price=update_data['entry_price'],
            size=update_data['size'],
            commission=update_data['commission'],
            slippage=update_data['slippage'],
            # ... other params
        )
```

### Configuration Requirements

```yaml
# Slippage
slippage_model: "bps"              # "bps" or "volume"
slippage_bps: 5.0                  # Basis points

# Volume-Based Slippage
volume_participation_limit_pct: 10.0  # Max % of bar volume

# Commission
commission_per_trade: 1.0          # $ per trade
```

### Usage Example

```python
from execution_engine import (
    fill_market_order,
    validate_order,
    update_position_from_fill,
    Order,
    Fill
)

# Create order
order = Order(
    symbol="SPY",
    direction="LONG",
    order_type="MARKET",
    size=100,
    timestamp=bar.timestamp
)

# Validate
valid, reason = validate_order(order, bar, config)
if not valid:
    print(f"Order rejected: {reason}")
    return

# Execute
fill = fill_market_order(order, bar, config, use_realistic_fills=True)

print(f"Filled {fill.fill_size} shares at ${fill.fill_price:.2f}")
print(f"Slippage: ${fill.slippage:.2f}")
print(f"Commission: ${fill.commission:.2f}")
print(f"Total cost: ${fill.total_cost:.2f}")

# Update position
update_data = update_position_from_fill(fill)
position = position_manager.open_position(**update_data)
```

### Features

✅ **Realistic Execution Simulation**
- Close price fills (realistic)
- Open price fills (optimistic)
- Configurable execution model

✅ **Slippage Models**
- BPS model (fixed percentage)
- Volume-based (market impact)
- Extensible for custom models

✅ **Cost Tracking**
- Slippage calculation
- Commission calculation
- Effective price calculation

✅ **Order Validation**
- Size validation
- Volume checks
- Price range checks (limit orders)

✅ **Position Integration**
- Opening position data
- Closing position P&L
- Seamless with PositionManager

✅ **Reusable Architecture**
- Works with backtesting
- Works with paper trading
- Adaptable for live trading

---
