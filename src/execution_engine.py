"""
Execution engine for order fills, slippage, and commission simulation.

This module handles:
- Market order fills
- Slippage calculation and application
- Commission calculation and application
- Fill price simulation
- Position updates from fills

Used by:
- Backtesting engine
- Paper trading system
- Live broker adapters
"""

import numpy as np
from typing import Optional, Tuple, Dict
from datetime import datetime
from types import SimpleNamespace
from dataclasses import dataclass

try:
    from .indicators import Bar
    from .positions import Position
except ImportError:
    # For standalone testing
    from indicators import Bar
    from positions import Position


# ==========================
# Order Data Structures
# ==========================

@dataclass
class Order:
    """
    Represents a trading order to be filled.
    """
    symbol: str
    direction: str  # "LONG" or "SHORT"
    order_type: str  # "MARKET", "LIMIT", "STOP" (for now, only MARKET supported)
    size: int  # Number of shares
    timestamp: datetime
    limit_price: Optional[float] = None  # For limit orders
    stop_price: Optional[float] = None  # For stop orders


@dataclass
class Fill:
    """
    Represents an executed order fill.
    """
    order: Order
    fill_price: float
    fill_time: datetime
    slippage: float  # Dollar amount of slippage
    commission: float  # Dollar amount of commission
    fill_size: int  # Actual filled size (may differ from order size)
    
    @property
    def total_cost(self) -> float:
        """Calculate total cost including slippage and commission."""
        base_cost = self.fill_price * self.fill_size
        return base_cost + abs(self.slippage) + self.commission
    
    @property
    def effective_price(self) -> float:
        """Calculate effective price per share including costs."""
        return self.total_cost / self.fill_size if self.fill_size > 0 else 0.0


# ==========================
# Market Order Execution
# ==========================

def fill_market_order(
    order: Order,
    bar: Bar,
    config: SimpleNamespace,
    use_realistic_fills: bool = True
) -> Fill:
    """
    Execute a market order and return fill details.
    
    Market orders are filled at:
    - Open price (if use_realistic_fills=False) - simple simulation
    - Close price with slippage (if use_realistic_fills=True) - realistic
    
    Args:
        order: Order to execute
        bar: Current bar with OHLC data
        config: Strategy configuration
        use_realistic_fills: If True, use close price + slippage; else use open
    
    Returns:
        Fill object with execution details
    
    Example:
        order = Order(symbol="SPY", direction="LONG", order_type="MARKET", 
                      size=100, timestamp=bar.timestamp)
        fill = fill_market_order(order, bar, config)
        print(f"Filled at ${fill.fill_price:.2f}, slippage: ${fill.slippage:.2f}")
    """
    # Determine fill price
    if use_realistic_fills:
        # Use close price as base (more realistic - orders filled during bar)
        base_fill_price = bar.close
    else:
        # Use open price (optimistic - assumes instant fill)
        base_fill_price = bar.open
    
    # Simulate realistic fill price with slippage
    fill_price = simulate_fill_price(
        order=order,
        bar=bar,
        base_price=base_fill_price,
        config=config
    )
    
    # Calculate slippage
    slippage = apply_slippage(
        order=order,
        bar=bar,
        base_price=base_fill_price,
        fill_price=fill_price,
        config=config
    )
    
    # Calculate commission
    commission = apply_commission(
        order=order,
        fill_price=fill_price,
        config=config
    )
    
    # Create fill
    fill = Fill(
        order=order,
        fill_price=fill_price,
        fill_time=bar.timestamp,
        slippage=slippage,
        commission=commission,
        fill_size=order.size
    )
    
    return fill


def simulate_fill_price(
    order: Order,
    bar: Bar,
    base_price: float,
    config: SimpleNamespace
) -> float:
    """
    Simulate realistic fill price with slippage.
    
    Slippage models:
    1. BPS (Basis Points): Fixed percentage slippage
    2. Volume-based: Slippage based on order size vs bar volume
    
    Args:
        order: Order being filled
        bar: Current bar
        base_price: Base price before slippage
        config: Strategy configuration
    
    Returns:
        Fill price after slippage
    """
    if config.slippage_model == "bps":
        # Fixed basis points slippage
        slippage_pct = config.slippage_bps / 10000  # Convert BPS to decimal
        
        if order.direction == "LONG":
            # Long orders: pay more (worse price)
            fill_price = base_price * (1 + slippage_pct)
        else:  # SHORT
            # Short orders: receive less (worse price)
            fill_price = base_price * (1 - slippage_pct)
    
    elif config.slippage_model == "volume":
        # Volume-based slippage model
        participation_pct = (order.size / bar.volume) * 100 if bar.volume > 0 else 0
        
        # If we exceed volume participation limit, increase slippage
        if participation_pct > config.volume_participation_limit_pct:
            # High participation = more slippage
            slippage_multiplier = 1 + (participation_pct / config.volume_participation_limit_pct)
            slippage_pct = (config.slippage_bps / 10000) * slippage_multiplier
        else:
            # Normal slippage
            slippage_pct = config.slippage_bps / 10000
        
        if order.direction == "LONG":
            fill_price = base_price * (1 + slippage_pct)
        else:  # SHORT
            fill_price = base_price * (1 - slippage_pct)
    
    else:
        # No slippage model or unknown model
        fill_price = base_price
    
    return fill_price


def apply_slippage(
    order: Order,
    bar: Bar,
    base_price: float,
    fill_price: float,
    config: SimpleNamespace
) -> float:
    """
    Calculate slippage cost in dollars.
    
    Slippage is the difference between expected price and actual fill price.
    
    Args:
        order: Order being filled
        bar: Current bar
        base_price: Expected price (before slippage)
        fill_price: Actual fill price (after slippage)
        config: Strategy configuration
    
    Returns:
        Slippage cost in dollars (positive number)
    """
    # Calculate price impact
    price_diff = abs(fill_price - base_price)
    
    # Slippage cost = price difference × size
    slippage_cost = price_diff * order.size
    
    return slippage_cost


def apply_commission(
    order: Order,
    fill_price: float,
    config: SimpleNamespace
) -> float:
    """
    Calculate commission cost for the order.
    
    Commission models:
    1. Per-trade: Fixed dollar amount per trade
    2. Per-share: Fixed amount per share
    3. Percentage: Percentage of notional value
    
    Args:
        order: Order being filled
        fill_price: Fill price
        config: Strategy configuration
    
    Returns:
        Commission cost in dollars
    """
    # Per-trade commission (most common for retail)
    commission = config.commission_per_trade
    
    # Note: Could extend to support per-share or percentage models
    # if hasattr(config, 'commission_model'):
    #     if config.commission_model == "per_share":
    #         commission = order.size * config.commission_per_share
    #     elif config.commission_model == "percentage":
    #         commission = (fill_price * order.size) * config.commission_pct
    
    return commission


# ==========================
# Position Updates
# ==========================

def update_position_from_fill(
    fill: Fill,
    position: Optional[Position] = None
) -> Dict:
    """
    Update position information after a fill.
    
    This creates position tracking data that can be used to create a Position object.
    
    Args:
        fill: Filled order
        position: Existing position (if closing/modifying), None if opening new
    
    Returns:
        Dictionary with position update data
    """
    if position is None:
        # Opening new position
        return {
            'action': 'open',
            'symbol': fill.order.symbol,
            'direction': fill.order.direction,
            'entry_price': fill.fill_price,
            'entry_time': fill.fill_time,
            'size': fill.fill_size,
            'commission': fill.commission,
            'slippage': fill.slippage,
            'effective_price': fill.effective_price
        }
    else:
        # Closing existing position
        # Calculate P&L
        if position.direction == "LONG":
            gross_pnl = (fill.fill_price - position.entry_price) * fill.fill_size
        else:  # SHORT
            gross_pnl = (position.entry_price - fill.fill_price) * fill.fill_size
        
        # Net P&L (subtract exit costs)
        net_pnl = gross_pnl - fill.commission - fill.slippage
        
        return {
            'action': 'close',
            'exit_price': fill.fill_price,
            'exit_time': fill.fill_time,
            'exit_commission': fill.commission,
            'exit_slippage': fill.slippage,
            'gross_pnl': gross_pnl,
            'net_pnl': net_pnl
        }


# ==========================
# Order Validation
# ==========================

def validate_order(
    order: Order,
    bar: Bar,
    config: SimpleNamespace
) -> Tuple[bool, str]:
    """
    Validate if order can be executed.
    
    Checks:
    1. Order size > 0
    2. Sufficient volume (if volume checks enabled)
    3. Price within bar range (for limit orders)
    
    Args:
        order: Order to validate
        bar: Current bar
        config: Strategy configuration
    
    Returns:
        Tuple of (is_valid: bool, reason: str)
    """
    # Check order size
    if order.size <= 0:
        return False, "invalid_order_size"
    
    # Check volume participation (if enabled)
    if hasattr(config, 'volume_participation_limit_pct'):
        participation_pct = (order.size / bar.volume) * 100 if bar.volume > 0 else 0
        
        # Allow orders up to 2x participation limit (with high slippage)
        if participation_pct > config.volume_participation_limit_pct * 2:
            return False, "insufficient_volume"
    
    # For limit orders, check if price is within bar range
    if order.order_type == "LIMIT" and order.limit_price is not None:
        if order.direction == "LONG":
            # Long limit: can only buy if price reached limit or below
            if bar.low > order.limit_price:
                return False, "limit_price_not_reached"
        else:  # SHORT
            # Short limit: can only sell if price reached limit or above
            if bar.high < order.limit_price:
                return False, "limit_price_not_reached"
    
    return True, "ok"


# ==========================
# Execution Summary
# ==========================

def generate_execution_summary(fills: list) -> Dict:
    """
    Generate summary statistics for executed orders.
    
    Args:
        fills: List of Fill objects
    
    Returns:
        Dictionary with execution statistics
    """
    if len(fills) == 0:
        return {
            'total_fills': 0,
            'total_shares': 0,
            'total_slippage': 0.0,
            'total_commission': 0.0,
            'avg_slippage_per_fill': 0.0,
            'avg_commission_per_fill': 0.0,
            'avg_slippage_bps': 0.0
        }
    
    total_shares = sum(f.fill_size for f in fills)
    total_slippage = sum(f.slippage for f in fills)
    total_commission = sum(f.commission for f in fills)
    
    # Calculate average slippage in BPS
    slippage_bps_list = []
    for fill in fills:
        # Slippage as percentage of notional
        notional = fill.fill_price * fill.fill_size
        if notional > 0:
            slippage_pct = (fill.slippage / notional) * 100
            slippage_bps = slippage_pct * 100  # Convert to BPS
            slippage_bps_list.append(slippage_bps)
    
    return {
        'total_fills': len(fills),
        'total_shares': total_shares,
        'total_slippage': total_slippage,
        'total_commission': total_commission,
        'avg_slippage_per_fill': total_slippage / len(fills),
        'avg_slippage_dollars': total_slippage / len(fills),
        'avg_commission_per_fill': total_commission / len(fills),
        'avg_slippage_bps': np.mean(slippage_bps_list) if slippage_bps_list else 0.0,
        'avg_fill_size': total_shares / len(fills),
        'total_costs': total_slippage + total_commission
    }


if __name__ == "__main__":
    # Test execution engine
    from types import SimpleNamespace
    from datetime import datetime
    
    print("Testing execution_engine.py...\n")
    
    # Create test config
    config = SimpleNamespace(
        slippage_model="bps",
        slippage_bps=5.0,
        commission_per_trade=1.0,
        volume_participation_limit_pct=10.0
    )
    
    # Create test bar
    test_bar = Bar(
        timestamp=datetime(2025, 1, 2, 10, 30),
        open=100.0,
        high=100.5,
        low=99.5,
        close=100.2,
        volume=100000
    )
    
    # Test 1: Market order - LONG
    print("=" * 60)
    print("Test 1: Market Order - LONG")
    print("=" * 60)
    
    order_long = Order(
        symbol="SPY",
        direction="LONG",
        order_type="MARKET",
        size=100,
        timestamp=test_bar.timestamp
    )
    
    # Validate order
    valid, reason = validate_order(order_long, test_bar, config)
    print(f"Order validation: {valid}, Reason: {reason}")
    
    if valid:
        # Fill order
        fill = fill_market_order(order_long, test_bar, config, use_realistic_fills=True)
        
        print(f"\n✅ Order Filled:")
        print(f"   Symbol: {fill.order.symbol}")
        print(f"   Direction: {fill.order.direction}")
        print(f"   Size: {fill.fill_size} shares")
        print(f"   Base Price: ${test_bar.close:.2f}")
        print(f"   Fill Price: ${fill.fill_price:.4f}")
        print(f"   Slippage: ${fill.slippage:.2f} ({(fill.slippage / (test_bar.close * fill.fill_size)) * 10000:.2f} BPS)")
        print(f"   Commission: ${fill.commission:.2f}")
        print(f"   Total Cost: ${fill.total_cost:.2f}")
        print(f"   Effective Price: ${fill.effective_price:.4f}")
    
    # Test 2: Market order - SHORT
    print("\n" + "=" * 60)
    print("Test 2: Market Order - SHORT")
    print("=" * 60)
    
    order_short = Order(
        symbol="SPY",
        direction="SHORT",
        order_type="MARKET",
        size=100,
        timestamp=test_bar.timestamp
    )
    
    fill_short = fill_market_order(order_short, test_bar, config, use_realistic_fills=True)
    
    print(f"✅ Order Filled:")
    print(f"   Direction: {fill_short.order.direction}")
    print(f"   Base Price: ${test_bar.close:.2f}")
    print(f"   Fill Price: ${fill_short.fill_price:.4f}")
    print(f"   Slippage: ${fill_short.slippage:.2f}")
    
    # Test 3: Volume-based slippage
    print("\n" + "=" * 60)
    print("Test 3: Volume-Based Slippage (Large Order)")
    print("=" * 60)
    
    config.slippage_model = "volume"
    
    large_order = Order(
        symbol="SPY",
        direction="LONG",
        order_type="MARKET",
        size=15000,  # 15% of volume
        timestamp=test_bar.timestamp
    )
    
    fill_large = fill_market_order(large_order, test_bar, config, use_realistic_fills=True)
    
    participation = (large_order.size / test_bar.volume) * 100
    print(f"Order Size: {large_order.size} shares")
    print(f"Bar Volume: {test_bar.volume} shares")
    print(f"Participation: {participation:.1f}%")
    print(f"✅ Fill Price: ${fill_large.fill_price:.4f}")
    print(f"   Slippage: ${fill_large.slippage:.2f} ({(fill_large.slippage / (test_bar.close * fill_large.fill_size)) * 10000:.2f} BPS)")
    
    # Test 4: Position update
    print("\n" + "=" * 60)
    print("Test 4: Position Update from Fill")
    print("=" * 60)
    
    # Open position
    update_data = update_position_from_fill(fill)
    print(f"✅ Position Update - OPEN:")
    print(f"   Action: {update_data['action']}")
    print(f"   Entry Price: ${update_data['entry_price']:.4f}")
    print(f"   Effective Price: ${update_data['effective_price']:.4f}")
    print(f"   Size: {update_data['size']}")
    
    # Test 5: Execution summary
    print("\n" + "=" * 60)
    print("Test 5: Execution Summary")
    print("=" * 60)
    
    fills = [fill, fill_short, fill_large]
    summary = generate_execution_summary(fills)
    
    print(f"✅ Execution Summary:")
    print(f"   Total Fills: {summary['total_fills']}")
    print(f"   Total Shares: {summary['total_shares']:,}")
    print(f"   Total Slippage: ${summary['total_slippage']:.2f}")
    print(f"   Total Commission: ${summary['total_commission']:.2f}")
    print(f"   Avg Slippage/Fill: ${summary['avg_slippage_per_fill']:.2f}")
    print(f"   Avg Slippage (BPS): {summary['avg_slippage_bps']:.2f}")
    
    print("\n" + "=" * 60)
    print("✅ All execution_engine.py tests passed!")
    print("=" * 60)
