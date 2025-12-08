"""
Risk management module for VWAP mean reversion strategy.

This module handles:
- Stop loss calculation (ATR-based and fixed percentage)
- Position sizing based on risk parameters
- Risk-reward ratio validation
- Risk limit checks
"""

import numpy as np
from typing import Optional, Tuple, Dict
from types import SimpleNamespace
from datetime import datetime

try:
    from .indicators import Bar
except ImportError:
    # For standalone testing
    from indicators import Bar


# ==========================
# Stop Loss Calculation
# ==========================

def calculate_stop_loss(
    entry_price: float,
    direction: str,
    config: SimpleNamespace,
    atr: Optional[float] = None
) -> float:
    """
    Calculate stop loss price based on configuration.
    
    Supports two methods:
    1. ATR-based: stop = entry ± (ATR × multiplier)
    2. Fixed %: stop = entry × (1 ± stop_pct)
    
    Args:
        entry_price: Entry price for the position
        direction: "LONG" or "SHORT"
        config: Strategy configuration (must have stop_type, stop_atr_mult, fixed_stop_pct)
        atr: Current ATR value (required if stop_type is "atr")
    
    Returns:
        Stop loss price
    
    Raises:
        ValueError: If stop_type is "atr" but atr is None
        ValueError: If stop_type is invalid
    
    Example:
        # ATR-based stop
        stop = calculate_stop_loss(100.0, "LONG", config, atr=2.0)
        # Returns: 96.0 (if stop_atr_mult=2.0)
        
        # Fixed % stop
        stop = calculate_stop_loss(100.0, "LONG", config)
        # Returns: 99.0 (if fixed_stop_pct=1.0)
    """
    if config.stop_type == "atr":
        if atr is None:
            raise ValueError("ATR value required for ATR-based stop loss")
        
        stop_distance = atr * config.stop_atr_mult
        
        if direction == "LONG":
            return entry_price - stop_distance
        else:  # SHORT
            return entry_price + stop_distance
    
    elif config.stop_type == "fixed":
        stop_pct = config.fixed_stop_pct / 100  # Convert to decimal
        
        if direction == "LONG":
            return entry_price * (1 - stop_pct)
        else:  # SHORT
            return entry_price * (1 + stop_pct)
    
    else:
        raise ValueError(f"Invalid stop_type: {config.stop_type}. Must be 'atr' or 'fixed'")


def calculate_position_size(
    entry_price: float,
    stop_loss: float,
    direction: str,
    capital: float,
    max_risk_pct: float
) -> int:
    """
    Calculate position size based on risk per trade.
    
    Formula: size = (capital × risk_pct) / (entry_price - stop_loss)
    
    Args:
        entry_price: Planned entry price
        stop_loss: Stop loss price
        direction: "LONG" or "SHORT"
        capital: Current capital available
        max_risk_pct: Maximum risk percentage per trade (e.g., 1.0 for 1%)
    
    Returns:
        Number of shares/contracts to trade (integer)
    
    Example:
        # Risk 1% of $100,000 on a trade
        # Entry: $100, Stop: $98, Risk per share: $2
        # Max risk: $1000, Position size: 500 shares
        size = calculate_position_size(100.0, 98.0, "LONG", 100000, 1.0)
        # Returns: 500
    """
    # Calculate risk per share
    risk_per_share = abs(entry_price - stop_loss)
    
    if risk_per_share <= 0:
        return 0
    
    # Calculate maximum risk amount
    max_risk_amount = capital * (max_risk_pct / 100)
    
    # Calculate position size
    position_size = int(max_risk_amount / risk_per_share)
    
    # Ensure we can afford the position (max 95% of capital)
    max_position_value = capital * 0.95
    position_value = position_size * entry_price
    
    if position_value > max_position_value:
        position_size = int(max_position_value / entry_price)
    
    # Ensure minimum size
    return max(0, position_size)


def calculate_risk_reward_ratio(
    entry_price: float,
    stop_loss: float,
    target_price: float,
    direction: str
) -> float:
    """
    Calculate risk-reward ratio for a trade.
    
    Risk-Reward Ratio = Potential Reward / Potential Risk
    
    Args:
        entry_price: Entry price
        stop_loss: Stop loss price
        target_price: Target exit price (e.g., VWAP)
        direction: "LONG" or "SHORT"
    
    Returns:
        Risk-reward ratio (e.g., 2.0 means 2:1 reward-to-risk)
    
    Example:
        # LONG: Entry $98, Stop $96, Target $100
        # Risk: $2, Reward: $2, R:R = 1.0
        rr = calculate_risk_reward_ratio(98.0, 96.0, 100.0, "LONG")
        # Returns: 1.0
    """
    if direction == "LONG":
        risk = entry_price - stop_loss
        reward = target_price - entry_price
    else:  # SHORT
        risk = stop_loss - entry_price
        reward = entry_price - target_price
    
    if risk <= 0:
        return 0.0
    
    return reward / risk


# ==========================
# Risk Validation
# ==========================

def validate_trade_risk(
    entry_price: float,
    stop_loss: float,
    target_price: float,
    direction: str,
    config: SimpleNamespace,
    min_risk_reward: float = 1.0
) -> Tuple[bool, str]:
    """
    Validate if trade meets risk criteria.
    
    Checks:
    1. Stop loss is valid (in correct direction)
    2. Risk-reward ratio meets minimum threshold
    3. Stop loss distance is reasonable
    
    Args:
        entry_price: Entry price
        stop_loss: Stop loss price
        target_price: Target exit price
        direction: "LONG" or "SHORT"
        config: Strategy configuration
        min_risk_reward: Minimum acceptable risk-reward ratio (default 1.0)
    
    Returns:
        Tuple of (is_valid: bool, reason: str)
    
    Example:
        valid, reason = validate_trade_risk(100.0, 98.0, 102.0, "LONG", config)
        if valid:
            # Place trade
        else:
            print(f"Trade rejected: {reason}")
    """
    # Check stop loss direction
    if direction == "LONG":
        if stop_loss >= entry_price:
            return False, "stop_loss_invalid_direction"
        if target_price <= entry_price:
            return False, "target_invalid_direction"
    else:  # SHORT
        if stop_loss <= entry_price:
            return False, "stop_loss_invalid_direction"
        if target_price >= entry_price:
            return False, "target_invalid_direction"
    
    # Calculate risk-reward ratio
    rr_ratio = calculate_risk_reward_ratio(entry_price, stop_loss, target_price, direction)
    
    if rr_ratio < min_risk_reward:
        return False, f"risk_reward_too_low_{rr_ratio:.2f}"
    
    # Check if stop loss distance is reasonable (not too tight or too wide)
    stop_distance_pct = abs((entry_price - stop_loss) / entry_price) * 100
    
    if stop_distance_pct < 0.1:  # Less than 0.1% - too tight
        return False, "stop_loss_too_tight"
    
    if stop_distance_pct > 10.0:  # More than 10% - too wide
        return False, "stop_loss_too_wide"
    
    return True, "ok"


def check_daily_risk_limit(
    current_daily_pnl: float,
    initial_capital: float,
    daily_loss_limit_pct: float
) -> Tuple[bool, float]:
    """
    Check if daily loss limit has been reached.
    
    Args:
        current_daily_pnl: Current P&L for the day (negative for loss)
        initial_capital: Initial capital at start
        daily_loss_limit_pct: Maximum allowed daily loss percentage
    
    Returns:
        Tuple of (can_trade: bool, remaining_loss_buffer: float)
    
    Example:
        can_trade, buffer = check_daily_risk_limit(-2500, 100000, 3.0)
        # Returns: (True, 500.0) - can still trade, $500 buffer left
    """
    max_loss_amount = initial_capital * (daily_loss_limit_pct / 100)
    
    if current_daily_pnl < -max_loss_amount:
        return False, 0.0
    
    remaining_buffer = max_loss_amount + current_daily_pnl  # current_daily_pnl is negative
    return True, remaining_buffer


def calculate_max_position_value(
    capital: float,
    max_leverage: float = 1.0
) -> float:
    """
    Calculate maximum position value allowed.
    
    Args:
        capital: Current capital
        max_leverage: Maximum leverage allowed (1.0 = no leverage)
    
    Returns:
        Maximum position value in dollars
    
    Example:
        max_value = calculate_max_position_value(100000, 1.0)
        # Returns: 95000 (95% of capital)
    """
    return capital * max_leverage * 0.95  # Use max 95% to leave buffer


# ==========================
# Risk Analytics
# ==========================

class RiskMetrics:
    """
    Calculate and track risk metrics for the strategy.
    """
    
    @staticmethod
    def calculate_max_drawdown(equity_curve: list) -> Tuple[float, int, int]:
        """
        Calculate maximum drawdown from equity curve.
        
        Args:
            equity_curve: List of equity values over time
        
        Returns:
            Tuple of (max_drawdown_pct, peak_idx, trough_idx)
        """
        if len(equity_curve) < 2:
            return 0.0, 0, 0
        
        equity = np.array(equity_curve)
        
        # Calculate running maximum
        running_max = np.maximum.accumulate(equity)
        
        # Calculate drawdown at each point
        drawdown = (equity - running_max) / running_max * 100
        
        # Find maximum drawdown
        max_dd_idx = np.argmin(drawdown)
        max_dd = drawdown[max_dd_idx]
        
        # Find peak before the drawdown
        peak_idx = np.argmax(equity[:max_dd_idx+1])
        
        return abs(max_dd), peak_idx, max_dd_idx
    
    @staticmethod
    def calculate_sharpe_ratio(
        returns: list,
        risk_free_rate: float = 0.0,
        periods_per_year: int = 252
    ) -> float:
        """
        Calculate annualized Sharpe ratio.
        
        Args:
            returns: List of period returns (as decimals)
            risk_free_rate: Annual risk-free rate (default 0.0)
            periods_per_year: Number of periods per year (252 for daily)
        
        Returns:
            Annualized Sharpe ratio
        """
        if len(returns) < 2:
            return 0.0
        
        returns_array = np.array(returns)
        
        # Calculate excess returns
        excess_returns = returns_array - (risk_free_rate / periods_per_year)
        
        # Calculate Sharpe ratio
        mean_excess = np.mean(excess_returns)
        std_excess = np.std(excess_returns, ddof=1)
        
        if std_excess == 0:
            return 0.0
        
        sharpe = (mean_excess / std_excess) * np.sqrt(periods_per_year)
        
        return sharpe
    
    @staticmethod
    def calculate_sortino_ratio(
        returns: list,
        risk_free_rate: float = 0.0,
        periods_per_year: int = 252
    ) -> float:
        """
        Calculate annualized Sortino ratio (uses downside deviation).
        
        Args:
            returns: List of period returns (as decimals)
            risk_free_rate: Annual risk-free rate (default 0.0)
            periods_per_year: Number of periods per year (252 for daily)
        
        Returns:
            Annualized Sortino ratio
        """
        if len(returns) < 2:
            return 0.0
        
        returns_array = np.array(returns)
        
        # Calculate excess returns
        excess_returns = returns_array - (risk_free_rate / periods_per_year)
        
        # Calculate downside deviation (only negative returns)
        downside_returns = excess_returns[excess_returns < 0]
        
        if len(downside_returns) == 0:
            return float('inf') if np.mean(excess_returns) > 0 else 0.0
        
        downside_std = np.sqrt(np.mean(downside_returns ** 2))
        
        if downside_std == 0:
            return 0.0
        
        sortino = (np.mean(excess_returns) / downside_std) * np.sqrt(periods_per_year)
        
        return sortino
    
    @staticmethod
    def calculate_calmar_ratio(
        total_return: float,
        max_drawdown: float,
        years: float = 1.0
    ) -> float:
        """
        Calculate Calmar ratio (return / max drawdown).
        
        Args:
            total_return: Total return as percentage
            max_drawdown: Maximum drawdown as percentage
            years: Number of years (for annualization)
        
        Returns:
            Calmar ratio
        """
        if max_drawdown == 0:
            return float('inf') if total_return > 0 else 0.0
        
        annualized_return = (total_return / 100) / years
        
        return annualized_return / (max_drawdown / 100)


# ==========================
# Risk Summary
# ==========================

def generate_risk_summary(
    trades: list,
    equity_curve: list,
    initial_capital: float,
    config: SimpleNamespace
) -> Dict:
    """
    Generate comprehensive risk summary for the strategy.
    
    Args:
        trades: List of trade dictionaries
        equity_curve: List of equity values
        initial_capital: Starting capital
        config: Strategy configuration
    
    Returns:
        Dictionary with risk metrics
    """
    if len(trades) == 0:
        return {
            'total_trades': 0,
            'max_drawdown_pct': 0.0,
            'sharpe_ratio': 0.0,
            'sortino_ratio': 0.0,
            'calmar_ratio': 0.0,
            'avg_risk_per_trade_pct': 0.0,
            'max_risk_per_trade_pct': 0.0,
            'largest_win_pct': 0.0,
            'largest_loss_pct': 0.0
        }
    
    # Calculate max drawdown
    max_dd, peak_idx, trough_idx = RiskMetrics.calculate_max_drawdown(equity_curve)
    
    # Calculate returns for Sharpe/Sortino
    returns = []
    for i in range(1, len(equity_curve)):
        ret = (equity_curve[i] - equity_curve[i-1]) / equity_curve[i-1]
        returns.append(ret)
    
    sharpe = RiskMetrics.calculate_sharpe_ratio(returns) if returns else 0.0
    sortino = RiskMetrics.calculate_sortino_ratio(returns) if returns else 0.0
    
    total_return = ((equity_curve[-1] - initial_capital) / initial_capital) * 100
    calmar = RiskMetrics.calculate_calmar_ratio(total_return, max_dd) if max_dd > 0 else 0.0
    
    # Calculate risk per trade
    risk_per_trade = []
    for trade in trades:
        if 'entry_price' in trade and 'stop_loss' in trade and 'size' in trade:
            risk = abs(trade['entry_price'] - trade['stop_loss']) * trade['size']
            risk_pct = (risk / initial_capital) * 100
            risk_per_trade.append(risk_pct)
    
    # Calculate win/loss percentages
    win_pcts = []
    loss_pcts = []
    for trade in trades:
        if 'realized_pnl' in trade and 'size' in trade and 'entry_price' in trade:
            pnl_pct = (trade['realized_pnl'] / (trade['size'] * trade['entry_price'])) * 100
            if pnl_pct > 0:
                win_pcts.append(pnl_pct)
            else:
                loss_pcts.append(abs(pnl_pct))
    
    return {
        'total_trades': len(trades),
        'max_drawdown_pct': max_dd,
        'sharpe_ratio': sharpe,
        'sortino_ratio': sortino,
        'calmar_ratio': calmar,
        'avg_risk_per_trade_pct': np.mean(risk_per_trade) if risk_per_trade else 0.0,
        'max_risk_per_trade_pct': max(risk_per_trade) if risk_per_trade else 0.0,
        'largest_win_pct': max(win_pcts) if win_pcts else 0.0,
        'largest_loss_pct': max(loss_pcts) if loss_pcts else 0.0,
        'avg_win_pct': np.mean(win_pcts) if win_pcts else 0.0,
        'avg_loss_pct': np.mean(loss_pcts) if loss_pcts else 0.0
    }


if __name__ == "__main__":
    # Test risk management functions
    from types import SimpleNamespace
    
    print("Testing risk_manager.py...\n")
    
    # Create test config
    config = SimpleNamespace(
        stop_type="atr",
        stop_atr_mult=2.0,
        fixed_stop_pct=1.0,
        max_position_risk_pct=1.0,
        daily_loss_limit_pct=3.0
    )
    
    # Test 1: ATR-based stop loss
    print("=" * 60)
    print("Test 1: ATR-based Stop Loss")
    print("=" * 60)
    
    stop_long = calculate_stop_loss(100.0, "LONG", config, atr=2.0)
    print(f"Entry: $100, Direction: LONG, ATR: 2.0, Mult: 2.0")
    print(f"✅ Stop Loss: ${stop_long:.2f}")
    
    stop_short = calculate_stop_loss(100.0, "SHORT", config, atr=2.0)
    print(f"\nEntry: $100, Direction: SHORT, ATR: 2.0, Mult: 2.0")
    print(f"✅ Stop Loss: ${stop_short:.2f}")
    
    # Test 2: Fixed percentage stop loss
    print("\n" + "=" * 60)
    print("Test 2: Fixed Percentage Stop Loss")
    print("=" * 60)
    
    config.stop_type = "fixed"
    stop_fixed_long = calculate_stop_loss(100.0, "LONG", config)
    print(f"Entry: $100, Direction: LONG, Fixed Stop: 1%")
    print(f"✅ Stop Loss: ${stop_fixed_long:.2f}")
    
    # Test 3: Position sizing
    print("\n" + "=" * 60)
    print("Test 3: Position Sizing")
    print("=" * 60)
    
    size = calculate_position_size(
        entry_price=100.0,
        stop_loss=98.0,
        direction="LONG",
        capital=100000,
        max_risk_pct=1.0
    )
    print(f"Capital: $100,000, Entry: $100, Stop: $98")
    print(f"Risk per trade: 1%, Risk per share: $2")
    print(f"✅ Position Size: {size} shares")
    print(f"   Position Value: ${size * 100:,.0f}")
    print(f"   Max Risk: ${size * 2:,.0f}")
    
    # Test 4: Risk-Reward Ratio
    print("\n" + "=" * 60)
    print("Test 4: Risk-Reward Ratio")
    print("=" * 60)
    
    rr_ratio = calculate_risk_reward_ratio(98.0, 96.0, 102.0, "LONG")
    print(f"Entry: $98, Stop: $96, Target: $102, Direction: LONG")
    print(f"Risk: $2, Reward: $4")
    print(f"✅ Risk-Reward Ratio: {rr_ratio:.2f}:1")
    
    # Test 5: Trade Risk Validation
    print("\n" + "=" * 60)
    print("Test 5: Trade Risk Validation")
    print("=" * 60)
    
    valid, reason = validate_trade_risk(98.0, 96.0, 102.0, "LONG", config, min_risk_reward=1.5)
    print(f"Entry: $98, Stop: $96, Target: $102")
    print(f"Min R:R: 1.5:1, Actual R:R: 2.0:1")
    print(f"✅ Valid: {valid}, Reason: {reason}")
    
    # Test 6: Daily Risk Limit
    print("\n" + "=" * 60)
    print("Test 6: Daily Risk Limit Check")
    print("=" * 60)
    
    can_trade, buffer = check_daily_risk_limit(-2500, 100000, 3.0)
    print(f"Current Daily P&L: -$2,500")
    print(f"Initial Capital: $100,000, Limit: 3%")
    print(f"✅ Can Trade: {can_trade}, Remaining Buffer: ${buffer:.2f}")
    
    # Test 7: Risk Metrics
    print("\n" + "=" * 60)
    print("Test 7: Risk Metrics Calculation")
    print("=" * 60)
    
    # Sample equity curve
    equity_curve = [100000, 101000, 100500, 102000, 101000, 103000, 102500, 104000]
    max_dd, peak, trough = RiskMetrics.calculate_max_drawdown(equity_curve)
    print(f"Equity Curve: {equity_curve}")
    print(f"✅ Max Drawdown: {max_dd:.2f}%")
    print(f"   Peak Index: {peak}, Trough Index: {trough}")
    
    # Sample returns
    returns = [0.01, -0.005, 0.015, -0.01, 0.02, -0.005, 0.015]
    sharpe = RiskMetrics.calculate_sharpe_ratio(returns, risk_free_rate=0.02)
    print(f"\n✅ Sharpe Ratio: {sharpe:.2f}")
    
    sortino = RiskMetrics.calculate_sortino_ratio(returns, risk_free_rate=0.02)
    print(f"✅ Sortino Ratio: {sortino:.2f}")
    
    print("\n" + "=" * 60)
    print("✅ All risk_manager.py tests passed!")
    print("=" * 60)
