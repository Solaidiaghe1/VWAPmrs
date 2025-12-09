"""
Position management and risk control module.

This module handles position tracking, sizing, risk management,
and daily P&L tracking for the VWAP mean reversion strategy.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from types import SimpleNamespace

try:
    from .indicators import Bar
except ImportError:
    # For standalone testing
    from indicators import Bar


# ==========================
# Data Structures
# ==========================

@dataclass
class Position:
    """
    Represents an open trading position.
    
    Tracks entry details, risk parameters, and P&L for a single position.
    """
    symbol: str
    direction: str  # "LONG" or "SHORT"
    entry_price: float
    entry_time: datetime
    entry_bar_idx: int
    size: int  # Number of shares/contracts
    stop_loss: float
    entry_vwap: float
    entry_z: float  # Z-score at entry
    position_id: str  # Unique identifier
    
    # Exit tracking (filled when position is closed)
    exit_price: Optional[float] = None
    exit_time: Optional[datetime] = None
    exit_reason: Optional[str] = None
    realized_pnl: Optional[float] = None
    commission: float = 0.0
    slippage: float = 0.0
    
    def unrealized_pnl(self, current_price: float) -> float:
        """
        Calculate unrealized P&L for open position.
        
        Args:
            current_price: Current market price
            
        Returns:
            Unrealized P&L (excludes commission/slippage)
        """
        if self.direction == "LONG":
            return (current_price - self.entry_price) * self.size
        else:  # SHORT
            return (self.entry_price - current_price) * self.size
    
    def is_stop_loss_hit(self, bar: Bar) -> bool:
        """
        Check if stop loss was hit during this bar.
        
        Args:
            bar: Current bar with OHLC data
            
        Returns:
            True if stop loss was triggered
        """
        if self.direction == "LONG":
            return bar.low <= self.stop_loss
        else:  # SHORT
            return bar.high >= self.stop_loss
    
    def holding_minutes(self, current_time: datetime) -> float:
        """
        Calculate how long position has been held.
        
        Args:
            current_time: Current timestamp
            
        Returns:
            Minutes held
        """
        return (current_time - self.entry_time).total_seconds() / 60
    
    def close_position(
        self,
        exit_price: float,
        exit_time: datetime,
        exit_reason: str,
        commission: float = 0.0,
        slippage: float = 0.0
    ) -> float:
        """
        Close position and calculate realized P&L.
        
        Args:
            exit_price: Exit price
            exit_time: Exit timestamp
            exit_reason: Reason for exit (e.g., "stop_loss", "signal_exit")
            commission: Commission paid (per side)
            slippage: Slippage cost
            
        Returns:
            Realized P&L (net of commission and slippage)
        """
        self.exit_price = exit_price
        self.exit_time = exit_time
        self.exit_reason = exit_reason
        self.commission = commission * 2  # Entry + Exit
        self.slippage = slippage * 2  # Entry + Exit
        
        # Calculate gross P&L
        if self.direction == "LONG":
            gross_pnl = (exit_price - self.entry_price) * self.size
        else:  # SHORT
            gross_pnl = (self.entry_price - exit_price) * self.size
        
        # Net P&L
        self.realized_pnl = gross_pnl - self.commission - self.slippage
        
        return self.realized_pnl
    
    def to_dict(self) -> dict:
        """Convert position to dictionary for logging/analysis."""
        return {
            'position_id': self.position_id,
            'symbol': self.symbol,
            'direction': self.direction,
            'entry_price': self.entry_price,
            'entry_time': self.entry_time,
            'entry_bar_idx': self.entry_bar_idx,
            'size': self.size,
            'stop_loss': self.stop_loss,
            'entry_vwap': self.entry_vwap,
            'entry_z': self.entry_z,
            'exit_price': self.exit_price,
            'exit_time': self.exit_time,
            'exit_reason': self.exit_reason,
            'realized_pnl': self.realized_pnl,
            'commission': self.commission,
            'slippage': self.slippage,
            'holding_minutes': self.holding_minutes(self.exit_time) if self.exit_time else None
        }


@dataclass
class DailyStats:
    """Track daily performance statistics."""
    date: datetime
    trades_count: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    commission_paid: float = 0.0
    slippage_paid: float = 0.0
    
    def update_from_position(self, position: Position):
        """Update stats when a position is closed."""
        if position.realized_pnl is None:
            return
        
        self.trades_count += 1
        self.total_pnl += position.realized_pnl
        self.commission_paid += position.commission
        self.slippage_paid += position.slippage
        
        if position.realized_pnl > 0:
            self.winning_trades += 1
            self.gross_profit += position.realized_pnl
        else:
            self.losing_trades += 1
            self.gross_loss += abs(position.realized_pnl)
    
    @property
    def win_rate(self) -> float:
        """Calculate win rate percentage."""
        if self.trades_count == 0:
            return 0.0
        return (self.winning_trades / self.trades_count) * 100
    
    @property
    def profit_factor(self) -> float:
        """Calculate profit factor (gross_profit / gross_loss)."""
        if self.gross_loss == 0:
            return float('inf') if self.gross_profit > 0 else 0.0
        return self.gross_profit / self.gross_loss


# ==========================
# Position Manager
# ==========================

class PositionManager:
    """
    Manages all open positions, risk controls, and position sizing.
    
    Handles:
    - Position tracking (per symbol and overall)
    - Position sizing based on risk parameters
    - Daily loss limits
    - Maximum position limits
    - Trade history and statistics
    """
    
    def __init__(self, config: SimpleNamespace, initial_capital: float):
        """
        Initialize position manager.
        
        Args:
            config: Strategy configuration (dot-accessible)
            initial_capital: Starting capital
        """
        self.config = config
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        
        # Position tracking
        self.open_positions: Dict[str, List[Position]] = {}  # symbol -> [positions]
        self.closed_positions: List[Position] = []
        self.position_counter = 0  # For generating unique IDs
        
        # Daily tracking
        self.current_date: Optional[datetime] = None
        self.daily_stats: Dict[datetime, DailyStats] = {}
        self.daily_pnl: float = 0.0
        
        # Risk tracking
        self.max_capital_deployed: float = 0.0
        self.total_commission_paid: float = 0.0
        self.total_slippage_paid: float = 0.0
    
    def reset_daily_tracking(self, current_date: datetime):
        """
        Reset daily tracking for new trading day.
        
        Args:
            current_date: Current date
        """
        if self.current_date is None or current_date.date() != self.current_date.date():
            self.current_date = current_date
            self.daily_pnl = 0.0
            
            date_key = current_date.date()
            if date_key not in self.daily_stats:
                self.daily_stats[date_key] = DailyStats(date=current_date)
    
    def can_open_position(self, symbol: str) -> Tuple[bool, str]:
        """
        Check if new position can be opened based on risk limits.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Tuple of (can_open: bool, reason: str)
        """
        # Check daily loss limit
        loss_limit_amount = self.initial_capital * (self.config.daily_loss_limit_pct / 100)
        if self.daily_pnl < -loss_limit_amount:
            return False, "daily_loss_limit_reached"
        
        # Check max total positions
        total_open = sum(len(positions) for positions in self.open_positions.values())
        if total_open >= self.config.max_total_positions:
            return False, "max_total_positions_reached"
        
        # Check max positions per symbol
        symbol_positions = self.open_positions.get(symbol, [])
        if len(symbol_positions) >= self.config.max_positions_per_symbol:
            return False, "max_positions_per_symbol_reached"
        
        return True, "ok"
    
    def calculate_position_size(
        self,
        symbol: str,
        entry_price: float,
        stop_loss: float,
        direction: str
    ) -> int:
        """
        Calculate position size based on risk parameters.
        
        Uses fixed percentage risk per trade (config.max_position_risk_pct).
        
        Args:
            symbol: Trading symbol
            entry_price: Planned entry price
            stop_loss: Stop loss price
            direction: "LONG" or "SHORT"
            
        Returns:
            Number of shares/contracts to trade
        """
        # Calculate risk per share
        risk_per_share = abs(entry_price - stop_loss)
        
        if risk_per_share <= 0:
            return 0
        
        # Calculate max risk amount
        max_risk_amount = self.current_capital * (self.config.max_position_risk_pct / 100)
        
        # Calculate position size
        position_size = int(max_risk_amount / risk_per_share)
        
        # Ensure we can afford the position
        position_value = position_size * entry_price
        max_position_value = self.current_capital * 0.95  # Use max 95% of capital
        
        if position_value > max_position_value:
            position_size = int(max_position_value / entry_price)
        
        # Minimum position size
        if position_size < 1:
            position_size = 0
        
        return position_size
    
    def open_position(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        entry_time: datetime,
        entry_bar_idx: int,
        stop_loss: float,
        entry_vwap: float,
        entry_z: float,
        size: Optional[int] = None
    ) -> Optional[Position]:
        """
        Open a new position.
        
        Args:
            symbol: Trading symbol
            direction: "LONG" or "SHORT"
            entry_price: Entry price
            entry_time: Entry timestamp
            entry_bar_idx: Bar index at entry
            stop_loss: Stop loss price
            entry_vwap: VWAP at entry
            entry_z: Z-score at entry
            size: Position size (if None, will auto-calculate)
            
        Returns:
            Position object if opened, None if cannot open
        """
        # Check if can open
        can_open, reason = self.can_open_position(symbol)
        if not can_open:
            return None
        
        # Calculate size if not provided
        if size is None:
            size = self.calculate_position_size(symbol, entry_price, stop_loss, direction)
        
        if size <= 0:
            return None
        
        # Create position
        position = Position(
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            entry_time=entry_time,
            entry_bar_idx=entry_bar_idx,
            size=size,
            stop_loss=stop_loss,
            entry_vwap=entry_vwap,
            entry_z=entry_z,
            position_id=f"{symbol}_{self.position_counter}_{entry_time.strftime('%Y%m%d_%H%M%S')}"
        )
        
        self.position_counter += 1
        
        # Add to tracking
        if symbol not in self.open_positions:
            self.open_positions[symbol] = []
        self.open_positions[symbol].append(position)
        
        # Update capital deployed
        position_value = size * entry_price
        self.max_capital_deployed = max(self.max_capital_deployed, position_value)
        
        return position
    
    def close_position(
        self,
        position: Position,
        exit_price: float,
        exit_time: datetime,
        exit_reason: str,
        commission: Optional[float] = None,
        slippage: Optional[float] = None
    ) -> float:
        """
        Close an existing position.
        
        Args:
            position: Position to close
            exit_price: Exit price
            exit_time: Exit timestamp
            exit_reason: Reason for exit
            commission: Commission per trade (if None, use config)
            slippage: Slippage cost (if None, calculate from config)
            
        Returns:
            Realized P&L
        """
        # Calculate commission
        if commission is None:
            commission = self.config.commission_per_trade
        
        # Calculate slippage
        if slippage is None:
            slippage = self._calculate_slippage(position, exit_price)
        
        # Close position
        realized_pnl = position.close_position(
            exit_price=exit_price,
            exit_time=exit_time,
            exit_reason=exit_reason,
            commission=commission,
            slippage=slippage
        )
        
        # Update tracking
        self.current_capital += realized_pnl
        self.daily_pnl += realized_pnl
        self.total_commission_paid += position.commission
        self.total_slippage_paid += position.slippage
        
        # Update daily stats
        if self.current_date:
            date_key = self.current_date.date()
            if date_key in self.daily_stats:
                self.daily_stats[date_key].update_from_position(position)
        
        # Move to closed positions
        self.open_positions[position.symbol].remove(position)
        if len(self.open_positions[position.symbol]) == 0:
            del self.open_positions[position.symbol]
        
        self.closed_positions.append(position)
        
        return realized_pnl
    
    def _calculate_slippage(self, position: Position, exit_price: float) -> float:
        """
        Calculate slippage cost based on config.
        
        Args:
            position: Position being closed
            exit_price: Exit price
            
        Returns:
            Total slippage cost (entry + exit)
        """
        if self.config.slippage_model == "bps":
            # Basis points slippage
            entry_slippage = position.entry_price * position.size * (self.config.slippage_bps / 10000)
            exit_slippage = exit_price * position.size * (self.config.slippage_bps / 10000)
            return entry_slippage + exit_slippage
        else:
            # Volume-based slippage (simplified - would need volume data)
            # For now, use BPS as fallback
            entry_slippage = position.entry_price * position.size * (self.config.slippage_bps / 10000)
            exit_slippage = exit_price * position.size * (self.config.slippage_bps / 10000)
            return entry_slippage + exit_slippage
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """
        Get first open position for symbol (for single-position-per-symbol strategies).
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Position or None
        """
        positions = self.open_positions.get(symbol, [])
        return positions[0] if positions else None
    
    def get_all_positions(self, symbol: Optional[str] = None) -> List[Position]:
        """
        Get all open positions, optionally filtered by symbol.
        
        Args:
            symbol: Optional symbol filter
            
        Returns:
            List of positions
        """
        if symbol:
            return self.open_positions.get(symbol, [])
        
        all_positions = []
        for positions in self.open_positions.values():
            all_positions.extend(positions)
        return all_positions
    
    def get_total_unrealized_pnl(self, current_prices: Dict[str, float]) -> float:
        """
        Calculate total unrealized P&L across all positions.
        
        Args:
            current_prices: Dict of symbol -> current price
            
        Returns:
            Total unrealized P&L
        """
        total_pnl = 0.0
        for symbol, positions in self.open_positions.items():
            if symbol in current_prices:
                for position in positions:
                    total_pnl += position.unrealized_pnl(current_prices[symbol])
        return total_pnl
    
    def get_performance_summary(self) -> dict:
        """
        Get overall performance summary.
        
        Returns:
            Dictionary with performance metrics
        """
        total_trades = len(self.closed_positions)
        if total_trades == 0:
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0.0,
                'total_pnl': 0.0,
                'gross_profit': 0.0,
                'gross_loss': 0.0,
                'profit_factor': 0.0,
                'avg_win': 0.0,
                'avg_loss': 0.0,
                'avg_trade': 0.0,
                'total_commission': 0.0,
                'total_slippage': 0.0,
                'current_capital': self.current_capital,
                'total_return_pct': 0.0
            }
        
        winning_trades = [p for p in self.closed_positions if p.realized_pnl > 0]
        losing_trades = [p for p in self.closed_positions if p.realized_pnl <= 0]
        
        total_pnl = sum(p.realized_pnl for p in self.closed_positions)
        gross_profit = sum(p.realized_pnl for p in winning_trades)
        gross_loss = abs(sum(p.realized_pnl for p in losing_trades))
        
        return {
            'total_trades': total_trades,
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'win_rate': (len(winning_trades) / total_trades) * 100,
            'total_pnl': total_pnl,
            'gross_profit': gross_profit,
            'gross_loss': gross_loss,
            'profit_factor': gross_profit / gross_loss if gross_loss > 0 else float('inf'),
            'avg_win': gross_profit / len(winning_trades) if winning_trades else 0.0,
            'avg_loss': gross_loss / len(losing_trades) if losing_trades else 0.0,
            'avg_trade': total_pnl / total_trades,
            'total_commission': self.total_commission_paid,
            'total_slippage': self.total_slippage_paid,
            'current_capital': self.current_capital,
            'final_capital': self.current_capital,
            'total_return': ((self.current_capital - self.initial_capital) / self.initial_capital) * 100,
            'total_return_pct': ((self.current_capital - self.initial_capital) / self.initial_capital) * 100
        }
    
    def export_trades(self) -> pd.DataFrame:
        """
        Export closed positions to DataFrame for analysis.
        
        Returns:
            DataFrame with trade history
        """
        import pandas as pd
        
        if not self.closed_positions:
            return pd.DataFrame()
        
        trades = []
        for pos in self.closed_positions:
            trades.append({
                'symbol': pos.symbol,
                'direction': pos.direction,
                'entry_time': pos.entry_time,
                'exit_time': pos.exit_time,
                'entry_price': pos.entry_price,
                'exit_price': pos.exit_price,
                'size': pos.size,
                'stop_loss': pos.stop_loss,
                'entry_vwap': pos.entry_vwap,
                'entry_z': pos.entry_z,
                'exit_reason': pos.exit_reason,
                'realized_pnl': pos.realized_pnl,
                'commission': pos.commission,
                'slippage': pos.slippage,
                'holding_minutes': (pos.exit_time - pos.entry_time).total_seconds() / 60,
                'position_id': pos.position_id
            })
        
        return pd.DataFrame(trades)
    
    def get_trade_history(self) -> List[dict]:
        """
        Get full trade history as list of dictionaries.
        
        Returns:
            List of trade dictionaries
        """
        return [position.to_dict() for position in self.closed_positions]


if __name__ == "__main__":
    # Test position manager
    from types import SimpleNamespace
    from datetime import datetime, timedelta
    
    # Create test config
    config = SimpleNamespace(
        max_position_risk_pct=1.0,
        daily_loss_limit_pct=3.0,
        max_positions_per_symbol=1,
        max_total_positions=5,
        commission_per_trade=1.0,
        slippage_bps=5.0,
        slippage_model="bps"
    )
    
    # Create position manager
    pm = PositionManager(config=config, initial_capital=100000)
    
    # Test opening position
    current_time = datetime(2025, 1, 2, 10, 0)
    pm.reset_daily_tracking(current_time)
    
    position = pm.open_position(
        symbol="SPY",
        direction="LONG",
        entry_price=100.0,
        entry_time=current_time,
        entry_bar_idx=10,
        stop_loss=99.0,
        entry_vwap=100.5,
        entry_z=-2.0
    )
    
    if position:
        print(f"✅ Opened position: {position.position_id}")
        print(f"   Size: {position.size} shares")
        print(f"   Risk: ${position.size * (position.entry_price - position.stop_loss):.2f}")
        
        # Test closing position
        exit_time = current_time + timedelta(minutes=30)
        pnl = pm.close_position(
            position=position,
            exit_price=101.0,
            exit_time=exit_time,
            exit_reason="signal_exit"
        )
        
        print(f"✅ Closed position")
        print(f"   Realized P&L: ${pnl:.2f}")
        print(f"   Current capital: ${pm.current_capital:.2f}")
    
    # Print performance summary
    summary = pm.get_performance_summary()
    print("\nPerformance Summary:")
    for key, value in summary.items():
        print(f"   {key}: {value}")
