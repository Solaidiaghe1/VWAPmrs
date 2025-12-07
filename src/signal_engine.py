"""
Signal generation engine for VWAP mean reversion strategy.

This module handles entry/exit signal generation, position management,
and strategy state tracking.
"""

import numpy as np
from typing import Optional, Tuple, List
from dataclasses import dataclass, field
from datetime import datetime
from types import SimpleNamespace

try:
    from .indicators import Bar, calculate_z_score, calculate_pct_deviation
except ImportError:
    # For standalone testing
    from indicators import Bar, calculate_z_score, calculate_pct_deviation


# ==========================
# Data Structures
# ==========================

@dataclass
class Position:
    """Represents an open trading position."""
    symbol: str
    direction: str  # "LONG" or "SHORT"
    entry_price: float
    entry_time: datetime
    entry_bar_idx: int
    size: int  # Number of shares
    stop_loss: float
    entry_vwap: float
    entry_z: float
    
    def unrealized_pnl(self, current_price: float) -> float:
        """Calculate unrealized P&L."""
        if self.direction == "LONG":
            return (current_price - self.entry_price) * self.size
        else:
            return (self.entry_price - current_price) * self.size
    
    def is_stop_loss_hit(self, bar: Bar) -> bool:
        """Check if stop loss was hit during this bar."""
        if self.direction == "LONG":
            return bar.low <= self.stop_loss
        else:
            return bar.high >= self.stop_loss


@dataclass
class StrategyState:
    """Tracks strategy state for a single symbol."""
    symbol: str
    current_position: Optional[Position] = None
    last_exit_bar_idx: int = -1
    bar_idx: int = 0
    session_start: Optional[datetime] = None
    session_end: Optional[datetime] = None
    
    # VWAP state
    cum_pv: float = 0.0
    cum_vol: float = 0.0
    vwap: float = 0.0
    
    # Rolling statistics
    deviation_history: List[float] = field(default_factory=list)
    volume_history: List[float] = field(default_factory=list)
    atr_values: List[float] = field(default_factory=list)
    
    # Daily tracking
    daily_pnl: float = 0.0
    trades_today: int = 0


# ==========================
# Entry Signal Generation
# ==========================

def generate_entry_signal(
    bar: Bar,
    vwap: float,
    z_score: float,
    pct_deviation: float,
    config: SimpleNamespace,
    state: StrategyState
) -> Optional[str]:
    """
    Generate entry signal (LONG, SHORT, or None).
    
    Args:
        bar: Current bar
        vwap: Current VWAP value
        z_score: Current z-score (from indicators.calculate_z_score)
        pct_deviation: Current percentage deviation (from indicators.calculate_pct_deviation)
        config: Strategy configuration (dot-accessible)
        state: Current strategy state
    
    Returns:
        "LONG", "SHORT", or None (no signal)
    
    Logic:
        1. Check entry filters (volume, time, cooldown)
        2. Check if already in position
        3. Check re-entry cooldown
        4. Generate signal based on signal_type (zscore or pct)
    """
    # Check entry filters first
    if not _check_entry_filters(bar, state, config):
        return None
    
    # Check if already in position
    if state.current_position is not None:
        return None
    
    # Check re-entry cooldown
    # NOTE: state.bar_idx must be set BEFORE calling this function
    bars_since_exit = state.bar_idx - state.last_exit_bar_idx
    if bars_since_exit < config.cooldown_bars:
        return None
    
    # Generate signal based on method
    if config.signal_type == 'zscore':
        if z_score > config.entry_z:
            return "SHORT"
        elif z_score < -config.entry_z:
            return "LONG"
    else:  # signal_type == 'pct'
        if pct_deviation > config.entry_pct:
            return "SHORT"
        elif pct_deviation < -config.entry_pct:
            return "LONG"
    
    return None


def _check_entry_filters(bar: Bar, state: StrategyState, config: SimpleNamespace) -> bool:
    """
    Check all entry filters.
    
    Filters:
    - Volume filter: Current volume must be >= X% of average volume
    - Market open wait: Must wait N minutes after session start
    - Minimum VWAP history: Require at least M bars before first trade
    """
    # Volume filter (optional - only if volume_history has enough data)
    volume_avg_window = getattr(config, 'volume_avg_window', 20)
    min_volume_pct_of_avg = getattr(config, 'min_volume_pct_of_avg', 50.0)
    
    if len(state.volume_history) >= volume_avg_window:
        avg_volume = np.mean(state.volume_history[-volume_avg_window:])
        min_volume = avg_volume * (min_volume_pct_of_avg / 100)
        if bar.volume < min_volume:
            return False
    
    # Market open wait filter
    if state.session_start is not None:
        minutes_since_open = (bar.timestamp - state.session_start).total_seconds() / 60
        if minutes_since_open < config.skip_open_minutes:
            return False
    
    # Minimum VWAP history filter (optional)
    min_vwap_bars = getattr(config, 'min_vwap_bars', 10)
    if state.bar_idx < min_vwap_bars:
        return False
    
    return True


# ==========================
# Exit Signal Generation
# ==========================

def check_exit_signal(
    position: Position,
    bar: Bar,
    z_score: float,
    pct_deviation: float,
    config: SimpleNamespace,
    state: StrategyState
) -> Tuple[bool, str]:
    """
    Check if position should be exited.
    
    Args:
        position: Current position
        bar: Current bar
        z_score: Current z-score
        pct_deviation: Current percentage deviation
        config: Strategy configuration
        state: Strategy state
    
    Returns:
        Tuple of (should_exit: bool, exit_reason: str)
    
    Exit reasons:
        - "stop_loss": Stop loss hit
        - "z_score_exit": Z-score crossed exit threshold
        - "pct_exit": Percentage deviation crossed exit threshold
        - "time_exit": Time-based exit (end of day)
        - "max_hold": Maximum holding period exceeded
    """
    # Stop loss check (highest priority)
    if position.is_stop_loss_hit(bar):
        return True, "stop_loss"
    
    # Time-based exit
    if state.session_end is not None:
        minutes_to_close = (state.session_end - bar.timestamp).total_seconds() / 60
        if minutes_to_close <= config.close_before_end_minutes:
            return True, "time_exit"
    
    # Maximum holding period
    holding_minutes = (bar.timestamp - position.entry_time).total_seconds() / 60
    if holding_minutes >= config.max_holding_minutes:
        return True, "max_hold"
    
    # Signal-based exit
    if config.signal_type == 'zscore':
        if position.direction == "LONG" and z_score >= -config.exit_z:
            return True, "z_score_exit"
        elif position.direction == "SHORT" and z_score <= config.exit_z:
            return True, "z_score_exit"
    else:  # signal_type == 'pct'
        if position.direction == "LONG" and pct_deviation >= -config.exit_pct:
            return True, "pct_exit"
        elif position.direction == "SHORT" and pct_deviation <= config.exit_pct:
            return True, "pct_exit"
    
    return False, ""


# ==========================
# Signal Calculation Helpers
# ==========================

def calculate_signal_inputs(
    bar: Bar,
    vwap: float,
    rolling_mean: float,
    rolling_std: float
) -> Tuple[float, float]:
    """
    Calculate z-score and percentage deviation for signal generation.
    
    Convenience function that calls indicators functions.
    
    Args:
        bar: Current bar
        vwap: Current VWAP
        rolling_mean: Rolling mean of deviations
        rolling_std: Rolling std of deviations
    
    Returns:
        Tuple of (z_score, pct_deviation)
    """
    z_score = calculate_z_score(bar.close, vwap, rolling_mean, rolling_std)
    pct_deviation = calculate_pct_deviation(bar.close, vwap)
    
    return z_score, pct_deviation


if __name__ == "__main__":
    # Test signal engine
    from datetime import datetime, timedelta
    from .config import load_config
    
    # Create test config
    try:
        from .config import load_config
        config = load_config("config.yaml")
    except:
        print("Could not load config.yaml, using test config")
        from types import SimpleNamespace
        config = SimpleNamespace(
            signal_type='zscore',
            entry_z=2.0,
            exit_z=0.3,
            entry_pct=0.002,
            exit_pct=0.0005,
            cooldown_bars=5,
            skip_open_minutes=15,
            close_before_end_minutes=15,
            max_holding_minutes=180,
            min_vwap_bars=10,
        )
    
    # Create test bar
    test_bar = Bar(
        timestamp=datetime(2025, 1, 2, 10, 0),
        open=100.0,
        high=100.5,
        low=99.8,
        close=100.2,
        volume=12000
    )
    
    # Create test state
    state = StrategyState(
        symbol="SPY",
        bar_idx=20,
        last_exit_bar_idx=10,
        session_start=datetime(2025, 1, 2, 9, 30),
        session_end=datetime(2025, 1, 2, 16, 0),
        vwap=100.0,
        volume_history=[10000, 11000, 12000, 13000, 14000] * 5
    )
    
    # Test signal generation
    vwap = 100.0
    z_score = 2.5  # Above entry threshold
    pct_deviation = 0.002
    
    signal = generate_entry_signal(test_bar, vwap, z_score, pct_deviation, config, state)
    print(f"Entry signal: {signal}")
    
    # Test exit signal
    position = Position(
        symbol="SPY",
        direction="LONG",
        entry_price=99.0,
        entry_time=datetime(2025, 1, 2, 9, 45),
        entry_bar_idx=15,
        size=100,
        stop_loss=98.0,
        entry_vwap=99.5,
        entry_z=2.0
    )
    
    state.current_position = position
    z_score_exit = 0.2  # Above exit threshold for LONG
    pct_deviation_exit = 0.0001
    
    should_exit, exit_reason = check_exit_signal(
        position, test_bar, z_score_exit, pct_deviation_exit, config, state
    )
    print(f"Should exit: {should_exit}, Reason: {exit_reason}")

