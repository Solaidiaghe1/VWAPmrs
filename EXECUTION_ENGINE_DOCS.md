# Execution Engine Documentation

## Overview
`execution_engine.py` is a production-ready order execution simulator that handles market order fills, slippage calculation, commission application, and position updates. This module is used by backtesting, paper trading, and can be adapted for live broker integration.

---

## Core Data Structures

### 1. `Order` (Dataclass)

Represents a trading order to be filled.

```python
@dataclass
class Order:
    symbol: str                 # Trading symbol
    direction: str              # "LONG" or "SHORT"
    order_type: str             # "MARKET", "LIMIT", "STOP"
    size: int                   # Number of shares
    timestamp: datetime         # Order creation time
    limit_price: Optional[float] = None   # For limit orders
    stop_price: Optional[float] = None    # For stop orders
```

**Example:**
```python
order = Order(
    symbol="SPY",
    direction="LONG",
    order_type="MARKET",
    size=100,
    timestamp=datetime.now()
)
```

---

### 2. `Fill` (Dataclass)

Represents an executed order with all costs.

```python
@dataclass
class Fill:
    order: Order                # Original order
    fill_price: float           # Actual fill price
    fill_time: datetime         # Fill timestamp
    slippage: float             # Slippage cost ($)
    commission: float           # Commission cost ($)
    fill_size: int              # Actual filled size
```

**Properties:**
- `total_cost` - Total cost including slippage and commission
- `effective_price` - Price per share including all costs

**Example:**
```python
fill = Fill(
    order=order,
    fill_price=100.05,
    fill_time=datetime.now(),
    slippage=5.0,
    commission=1.0,
    fill_size=100
)

print(f"Total cost: ${fill.total_cost:.2f}")
print(f"Effective price: ${fill.effective_price:.4f}")
```

---

## Main Functions

### 1. fill_market_order()

Execute a market order and return fill details.

```python
def fill_market_order(
    order: Order,
    bar: Bar,
    config: SimpleNamespace,
    use_realistic_fills: bool = True
) -> Fill
```

**Parameters:**
- `order` - Order to execute
- `bar` - Current OHLC bar
- `config` - Strategy configuration
- `use_realistic_fills` - If True, uses close + slippage; if False, uses open (optimistic)

**Returns:**
- `Fill` object with execution details

**Fill Price Logic:**
- **Realistic mode** (`use_realistic_fills=True`):
  - Uses `bar.close` as base price
  - Applies slippage
  - More realistic simulation
  
- **Optimistic mode** (`use_realistic_fills=False`):
  - Uses `bar.open` as base price
  - Still applies slippage
  - Assumes instant execution

**Example:**
```python
order = Order(
    symbol="SPY",
    direction="LONG",
    order_type="MARKET",
    size=100,
    timestamp=bar.timestamp
)

fill = fill_market_order(order, bar, config, use_realistic_fills=True)

print(f"Filled {fill.fill_size} shares at ${fill.fill_price:.2f}")
print(f"Slippage: ${fill.slippage:.2f}")
print(f"Commission: ${fill.commission:.2f}")
```

---

### 2. simulate_fill_price()

Simulate realistic fill price with slippage.

```python
def simulate_fill_price(
    order: Order,
    bar: Bar,
    base_price: float,
    config: SimpleNamespace
) -> float
```

**Slippage Models:**

#### A. BPS (Basis Points) Model
Fixed percentage slippage on all orders.

```python
config.slippage_model = "bps"
config.slippage_bps = 5.0  # 5 basis points = 0.05%
```

- **LONG orders**: Pay more (worse price)
  - `fill_price = base_price × (1 + slippage_bps/10000)`
  
- **SHORT orders**: Receive less (worse price)
  - `fill_price = base_price × (1 - slippage_bps/10000)`

**Example:**
```
Base price: $100.00
Slippage: 5 BPS
LONG fill: $100.05
SHORT fill: $99.95
```

#### B. Volume-Based Model
Slippage increases with order size relative to bar volume.

```python
config.slippage_model = "volume"
config.slippage_bps = 5.0
config.volume_participation_limit_pct = 10.0
```

**Logic:**
```python
participation_pct = (order.size / bar.volume) × 100

if participation_pct > volume_participation_limit_pct:
    # Increase slippage proportionally
    slippage_multiplier = 1 + (participation_pct / limit_pct)
    adjusted_slippage = base_slippage × slippage_multiplier
```

**Example:**
```
Bar volume: 100,000 shares
Order size: 15,000 shares (15% participation)
Limit: 10%
Multiplier: 1 + (15/10) = 2.5
Slippage: 5 BPS × 2.5 = 12.5 BPS
```

---

### 3. apply_slippage()

Calculate slippage cost in dollars.

```python
def apply_slippage(
    order: Order,
    bar: Bar,
    base_price: float,
    fill_price: float,
    config: SimpleNamespace
) -> float
```

**Formula:**
```python
price_diff = |fill_price - base_price|
slippage_cost = price_diff × order.size
```

**Example:**
```python
base_price = 100.00
fill_price = 100.05
order_size = 100

slippage = |100.05 - 100.00| × 100 = $5.00
```

---

### 4. apply_commission()

Calculate commission cost for the order.

```python
def apply_commission(
    order: Order,
    fill_price: float,
    config: SimpleNamespace
) -> float
```

**Current Model:**
- Per-trade commission (fixed dollar amount)
- `commission = config.commission_per_trade`

**Extensible to:**
- Per-share: `commission = order.size × per_share_rate`
- Percentage: `commission = (fill_price × order.size) × commission_pct`

**Example:**
```python
config.commission_per_trade = 1.0
commission = apply_commission(order, fill_price, config)
# Returns: 1.0
```

---

### 5. update_position_from_fill()

Create position update data after a fill.

```python
def update_position_from_fill(
    fill: Fill,
    position: Optional[Position] = None
) -> Dict
```

**Returns:**

#### Opening New Position (`position=None`)
```python
{
    'action': 'open',
    'symbol': 'SPY',
    'direction': 'LONG',
    'entry_price': 100.05,
    'entry_time': datetime(...),
    'size': 100,
    'commission': 1.0,
    'slippage': 5.0,
    'effective_price': 100.11
}
```

#### Closing Position (`position=Position(...)`)
```python
{
    'action': 'close',
    'exit_price': 102.00,
    'exit_time': datetime(...),
    'exit_commission': 1.0,
    'exit_slippage': 5.0,
    'gross_pnl': 195.0,   # (102.00 - 100.05) × 100
    'net_pnl': 189.0      # gross_pnl - commission - slippage
}
```

**Usage:**
```python
# Opening
fill = fill_market_order(order, bar, config)
update_data = update_position_from_fill(fill)

position = position_manager.open_position(
    symbol=update_data['symbol'],
    entry_price=update_data['entry_price'],
    # ... other params from update_data
)

# Closing
exit_order = Order(symbol="SPY", direction="LONG", ...)
exit_fill = fill_market_order(exit_order, bar, config)
close_data = update_position_from_fill(exit_fill, position)

position_manager.close_position(
    position=position,
    exit_price=close_data['exit_price'],
    exit_time=close_data['exit_time'],
    # ...
)
```

---

### 6. validate_order()

Validate if order can be executed.

```python
def validate_order(
    order: Order,
    bar: Bar,
    config: SimpleNamespace
) -> Tuple[bool, str]
```

**Validation Checks:**
1. Order size > 0
2. Sufficient volume (if enabled)
3. Price within bar range (for limit orders)

**Returns:**
- `(True, "ok")` - Order is valid
- `(False, reason)` - Order is invalid

**Rejection Reasons:**
- `"invalid_order_size"` - Size ≤ 0
- `"insufficient_volume"` - Order too large for bar volume
- `"limit_price_not_reached"` - Limit price not touched

**Example:**
```python
valid, reason = validate_order(order, bar, config)

if not valid:
    print(f"Order rejected: {reason}")
    return

# Proceed with execution
fill = fill_market_order(order, bar, config)
```

---

### 7. generate_execution_summary()

Generate summary statistics for executed orders.

```python
def generate_execution_summary(fills: list) -> Dict
```

**Returns:**
```python
{
    'total_fills': 150,
    'total_shares': 15000,
    'total_slippage': 750.0,
    'total_commission': 150.0,
    'avg_slippage_per_fill': 5.0,
    'avg_commission_per_fill': 1.0,
    'avg_slippage_bps': 5.0,
    'avg_fill_size': 100.0
}
```

**Usage:**
```python
# At end of backtest
fills = []  # Collect all Fill objects during backtest

summary = generate_execution_summary(fills)
print(f"Total slippage: ${summary['total_slippage']:.2f}")
print(f"Average slippage: {summary['avg_slippage_bps']:.2f} BPS")
```

---

## Integration Examples

### With Backtesting Engine

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
        
        # Validate order
        valid, reason = validate_order(order, bar, config)
        if not valid:
            continue
        
        # Fill order
        fill = fill_market_order(order, bar, config, use_realistic_fills=True)
        
        # Update position manager
        update_data = update_position_from_fill(fill)
        position = position_manager.open_position(
            symbol=update_data['symbol'],
            entry_price=update_data['entry_price'],
            # ... other params
        )
```

### With Paper Trading

```python
# Paper trading uses same execution engine
def execute_paper_trade(order, current_bar):
    # Use execution engine for realistic simulation
    fill = fill_market_order(order, current_bar, config, use_realistic_fills=True)
    
    # Log execution
    logger.info(f"Paper trade filled: {fill.order.symbol} @ ${fill.fill_price:.2f}")
    
    return fill
```

### With Live Broker Adapter

```python
# Adapt execution engine for live trading
class BrokerAdapter:
    def execute_order(self, order, current_bar):
        # Use execution engine to estimate costs before sending to broker
        simulated_fill = fill_market_order(order, current_bar, config)
        
        # Send to broker
        broker_order_id = self.broker.submit_order(order)
        
        # Wait for actual fill
        actual_fill = self.broker.wait_for_fill(broker_order_id)
        
        # Compare simulated vs actual
        slippage_diff = actual_fill.slippage - simulated_fill.slippage
        logger.info(f"Slippage estimate vs actual: ${slippage_diff:.2f}")
        
        return actual_fill
```

---

## Configuration Requirements

```yaml
# Slippage Configuration
slippage_model: "bps"            # "bps" or "volume"
slippage_bps: 5.0                # Basis points

# Volume-Based Slippage
volume_participation_limit_pct: 10.0   # Max % of bar volume

# Commission
commission_per_trade: 1.0        # $ per trade
```

---

## Best Practices

### 1. Slippage Model Selection

**Use BPS model for:**
- Liquid stocks/ETFs
- Standard position sizes
- Simplicity and consistency

**Use Volume model for:**
- Varying order sizes
- Less liquid instruments
- More realistic large order simulation

### 2. Realistic Fills

Always use `use_realistic_fills=True` for backtesting:
```python
fill = fill_market_order(order, bar, config, use_realistic_fills=True)
```

Using `False` gives optimistic results (fills at open price).

### 3. Order Validation

Always validate orders before execution:
```python
valid, reason = validate_order(order, bar, config)
if not valid:
    logger.warning(f"Order rejected: {reason}")
    continue
```

### 4. Cost Tracking

Track execution costs separately from P&L:
```python
total_slippage = sum(f.slippage for f in fills)
total_commission = sum(f.commission for f in fills)
gross_pnl = position.realized_pnl + total_slippage + total_commission
```

### 5. Slippage Analysis

Analyze slippage to optimize execution:
```python
summary = generate_execution_summary(fills)

if summary['avg_slippage_bps'] > 10.0:
    print("⚠️  High slippage - consider reducing order sizes")
```

---

## Testing

Run built-in tests:
```bash
cd /Users/solaidiaghe/Desktop/VWAPmrs/VWAPmrs/src
python3 execution_engine.py
```

**Tests cover:**
- ✅ Market order execution (LONG & SHORT)
- ✅ BPS slippage model
- ✅ Volume-based slippage model
- ✅ Commission calculation
- ✅ Position update from fills
- ✅ Order validation
- ✅ Execution summary generation

---

## Summary

`execution_engine.py` provides:
- ✅ Realistic order execution simulation
- ✅ Multiple slippage models (BPS & volume-based)
- ✅ Commission calculation
- ✅ Order validation
- ✅ Position update helpers
- ✅ Execution cost tracking
- ✅ Reusable across backtest/paper/live trading
- ✅ Comprehensive testing
- ✅ Production-ready code

**Ready for integration with backtesting engine!** 🚀
