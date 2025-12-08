"""
Technical indicators module.

This module implements VWAP, ATR, rolling statistics, and signal calculations
for the VWAP mean reversion strategy.

ARCHITECTURE:
- Batch mode: DataFrame → DataFrame/Series (for backtesting)
- Incremental mode: Bar → float (for live trading)
- ATR: Always uses DataFrames internally (even if called with Bar objects)
"""

import pandas as pd
import numpy as np
from typing import List, Tuple, Optional, Union
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Bar:
    """OHLCV bar data structure for incremental/live trading."""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    
    def typical_price(self) -> float:
        """Calculate typical price for VWAP (HLC/3)."""
        return (self.high + self.low + self.close) / 3.0


# ==========================
# VWAP Calculation
# ==========================

def compute_vwap(df: pd.DataFrame, use_typical_price: bool = True) -> pd.Series:
    """
    BATCH MODE: Calculate VWAP for a DataFrame (for backtesting).
    
    Args:
        df: DataFrame with OHLCV columns and DatetimeIndex
        use_typical_price: If True, use (H+L+C)/3, else use close
    
    Returns:
        Series of VWAP values (same index as input DataFrame)
    
    Note:
        - VWAP resets each session (call this per trading day)
        - Vectorized implementation for performance
    """
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("DataFrame must have DatetimeIndex")
    
    # Calculate price
    if use_typical_price:
        price = (df['high'] + df['low'] + df['close']) / 3.0
    else:
        price = df['close']
    
    # Calculate cumulative price * volume and cumulative volume
    cum_pv = (price * df['volume']).cumsum()
    cum_vol = df['volume'].cumsum()
    
    # Calculate VWAP (handle zero volume by forward-filling)
    vwap = cum_pv / cum_vol
    vwap = vwap.fillna(method='ffill').fillna(price)  # Forward fill, then use price if still NaN
    
    return vwap


def update_vwap(
    cum_pv: float,
    cum_vol: float,
    bar: Bar,
    use_typical_price: bool = True
) -> Tuple[float, float, float]:
    """
    INCREMENTAL MODE: Update VWAP for a single bar (for live trading).
    
    Args:
        cum_pv: Cumulative price * volume (maintain state)
        cum_vol: Cumulative volume (maintain state)
        bar: Current bar
        use_typical_price: If True, use (H+L+C)/3, else use close
    
    Returns:
        Tuple of (updated_cum_pv, updated_cum_vol, vwap)
    
    Note:
        - If volume is 0, keep previous VWAP (cum_pv and cum_vol unchanged)
        - Call this for each bar in sequence
    """
    price = bar.typical_price() if use_typical_price else bar.close
    
    if bar.volume > 0:
        cum_pv += price * bar.volume
        cum_vol += bar.volume
        vwap = cum_pv / cum_vol if cum_vol > 0 else price
    else:
        # If volume is 0, keep previous VWAP
        vwap = cum_pv / cum_vol if cum_vol > 0 else price
    
    return cum_pv, cum_vol, vwap


# ==========================
# ATR Calculation
# ==========================

def compute_atr(
    df: pd.DataFrame,
    period: int = 14,
    atr_timeframe: str = "10min",
    strategy_timeframe: str = "1min"
) -> pd.Series:
    """
    BATCH MODE: Calculate ATR for a DataFrame (for backtesting).
    
    IMPORTANT: ATR MUST operate on DataFrames internally.
    This function uses DataFrame operations for resampling and rolling windows.
    
    Args:
        df: DataFrame with OHLCV columns and DatetimeIndex
        period: ATR period (default 14, should come from config['stop_atr_window'])
        atr_timeframe: Timeframe for ATR calculation (e.g., "10min")
        strategy_timeframe: Strategy bar timeframe (e.g., "1min")
    
    Returns:
        Series of ATR values (same index as input DataFrame, forward-filled)
    
    Implementation:
        1. Resample bars to atr_timeframe (e.g., 1-min -> 10-min)
        2. Calculate TR and ATR on resampled bars
        3. Forward-fill ATR values back to strategy_timeframe frequency
    
    Formula:
        TR = max(high - low, abs(high - prev_close), abs(low - prev_close))
        ATR = SMA(TR, period) on resampled bars
    """
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("DataFrame must have DatetimeIndex")
    
    if atr_timeframe == strategy_timeframe:
        # No resampling needed - calculate directly
        return _compute_atr_direct(df, period)
    else:
        # Resample to ATR timeframe
        return _compute_atr_resampled(df, period, atr_timeframe, strategy_timeframe)


def update_atr(
    bar_buffer: List[Bar],
    period: int = 14,
    atr_timeframe: str = "10min",
    strategy_timeframe: str = "1min"
) -> float:
    """
    INCREMENTAL MODE: Update ATR for a rolling bar buffer (for live trading).
    
    IMPORTANT: ATR requires DataFrame operations internally.
    This function converts the bar buffer to DataFrame, computes ATR, then returns latest value.
    
    Args:
        bar_buffer: Rolling buffer of Bar objects (maintain in live trading)
        period: ATR period
        atr_timeframe: Timeframe for ATR calculation
        strategy_timeframe: Strategy bar timeframe
    
    Returns:
        Latest ATR value (float)
    
    Note:
        - bar_buffer should be maintained as a rolling window
        - Convert to DataFrame internally for ATR calculation
        - Returns only the most recent ATR value
    """
    if len(bar_buffer) < 2:
        return 0.0  # Need at least 2 bars for ATR
    
    # Convert bar buffer to DataFrame (ATR requires DataFrame operations)
    df = _bars_to_df(bar_buffer)
    
    # Compute ATR on DataFrame
    atr_series = compute_atr(df, period, atr_timeframe, strategy_timeframe)
    
    # Return latest value
    return float(atr_series.iloc[-1])


def _compute_atr_direct(df: pd.DataFrame, period: int) -> pd.Series:
    """Calculate ATR directly without resampling (DataFrame operations)."""
    # Calculate True Range
    tr = pd.Series(index=df.index, dtype=float)
    
    # First bar: TR = high - low
    tr.iloc[0] = df['high'].iloc[0] - df['low'].iloc[0]
    
    # Subsequent bars: TR = max(high - low, |high - prev_close|, |low - prev_close|)
    prev_close = df['close'].shift(1)
    tr.iloc[1:] = pd.concat([
        df['high'].iloc[1:] - df['low'].iloc[1:],
        (df['high'].iloc[1:] - prev_close.iloc[1:]).abs(),
        (df['low'].iloc[1:] - prev_close.iloc[1:]).abs()
    ], axis=1).max(axis=1)
    
    # Calculate ATR as rolling mean of TR
    atr = tr.rolling(window=period, min_periods=1).mean()
    
    return atr


def _compute_atr_resampled(
    df: pd.DataFrame,
    period: int,
    atr_timeframe: str,
    strategy_timeframe: str
) -> pd.Series:
    """Calculate ATR on resampled bars, then forward-fill to original frequency."""
    # Resample to ATR timeframe
    resampled = df.resample(atr_timeframe).agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    })
    
    # Calculate ATR on resampled bars
    atr_resampled = _compute_atr_direct(resampled, period)
    
    # Forward-fill ATR values to match original bar frequency
    # Reindex to original DataFrame index and forward-fill
    atr_forward_filled = atr_resampled.reindex(df.index, method='ffill')
    
    # Fill any remaining NaN with 0.0 (for bars before first resampled ATR)
    atr_forward_filled = atr_forward_filled.fillna(0.0)
    
    return atr_forward_filled


# ==========================
# Rolling Statistics
# ==========================

def update_rolling_stats(
    deviation_history: List[float],
    window: int,
    current_deviation: float
) -> Tuple[float, float]:
    """
    Calculate rolling mean and std of deviations.
    
    Args:
        deviation_history: List of previous deviations (maintain in StrategyState)
        window: Rolling window size
        current_deviation: Current bar's deviation
    
    Returns:
        Tuple of (rolling_mean, rolling_std)
    
    Note:
        - For first N bars (N < window), use expanding window
        - Handle division by zero (if std=0, return small epsilon)
        - Use sample std (ddof=1)
    """
    deviation_history.append(current_deviation)
    
    # Keep only last 'window' values
    if len(deviation_history) > window:
        deviation_history.pop(0)
    
    if len(deviation_history) < 2:
        return current_deviation, 0.0
    
    arr = np.array(deviation_history)
    mean = np.mean(arr)
    std = np.std(arr, ddof=1)  # Sample std
    
    # Handle division by zero
    if std == 0:
        std = 1e-8  # Small epsilon
    
    return mean, std


# ==========================
# Signal Calculations
# ==========================

def calculate_z_score(
    price: float,
    vwap: float,
    rolling_mean: float,
    rolling_std: float
) -> float:
    """
    Calculate z-score of price deviation from VWAP.
    
    Args:
        price: Current price (typically close)
        vwap: Current VWAP
        rolling_mean: Rolling mean of deviations
        rolling_std: Rolling std of deviations
    
    Returns:
        Z-score value
    """
    deviation = price - vwap
    if rolling_std == 0:
        return 0.0
    return (deviation - rolling_mean) / rolling_std


def calculate_pct_deviation(price: float, vwap: float) -> float:
    """
    Calculate percentage deviation from VWAP.
    
    Args:
        price: Current price
        vwap: Current VWAP
    
    Returns:
        Percentage deviation (e.g., 0.0015 for 0.15%)
    """
    if vwap == 0:
        return 0.0
    return (price - vwap) / vwap


# ==========================
# Convenience Functions for Backtest
# ==========================

def calculate_vwap(bars: list, use_typical_price: bool = True) -> float:
    """
    Calculate VWAP from a list of bars (convenience function for backtesting).
    
    Args:
        bars: List of Bar objects
        use_typical_price: If True, use (H+L+C)/3, else use close
    
    Returns:
        Current VWAP value
    """
    cum_pv = 0.0
    cum_vol = 0.0
    
    for bar in bars:
        price = bar.typical_price() if use_typical_price else bar.close
        if bar.volume > 0:
            cum_pv += price * bar.volume
            cum_vol += bar.volume
    
    return cum_pv / cum_vol if cum_vol > 0 else bars[-1].close


def calculate_atr(bars: list, window: int = 14) -> float:
    """
    Calculate ATR from a list of bars (convenience function for backtesting).
    
    Args:
        bars: List of Bar objects (should have at least window+1 bars)
        window: ATR period
    
    Returns:
        Current ATR value
    """
    if len(bars) < 2:
        return 0.0
    
    true_ranges = []
    for i in range(1, len(bars)):
        high_low = bars[i].high - bars[i].low
        high_close = abs(bars[i].high - bars[i-1].close)
        low_close = abs(bars[i].low - bars[i-1].close)
        tr = max(high_low, high_close, low_close)
        true_ranges.append(tr)
    
    # Use simple moving average of TRs for the window
    if len(true_ranges) < window:
        return sum(true_ranges) / len(true_ranges) if true_ranges else 0.0
    
    return sum(true_ranges[-window:]) / window


def calculate_vwap_df(df: pd.DataFrame, use_typical_price: bool = True) -> pd.Series:
    """
    Calculate VWAP for a DataFrame (returns Series).
    
    Convenience function for DataFrame-based workflows.
    """
    vwap_list = calculate_vwap(df, use_typical_price)
    return pd.Series(vwap_list, index=df.index if isinstance(df.index, pd.DatetimeIndex) else range(len(vwap_list)))


def calculate_atr_df(
    df: pd.DataFrame,
    period: int = 14,
    atr_timeframe: str = "10min",
    strategy_timeframe: str = "1min"
) -> pd.Series:
    """
    Calculate ATR for a DataFrame (returns Series).
    
    Convenience function for DataFrame-based workflows.
    """
    atr_list = calculate_atr(df, period, atr_timeframe, strategy_timeframe)
    return pd.Series(atr_list, index=df.index if isinstance(df.index, pd.DatetimeIndex) else range(len(atr_list)))


# ==========================
# Helper Functions
# ==========================

def _bars_to_df(bars: List[Bar]) -> pd.DataFrame:
    """Convert list of Bar objects to DataFrame."""
    data = {
        'timestamp': [bar.timestamp for bar in bars],
        'open': [bar.open for bar in bars],
        'high': [bar.high for bar in bars],
        'low': [bar.low for bar in bars],
        'close': [bar.close for bar in bars],
        'volume': [bar.volume for bar in bars],
    }
    df = pd.DataFrame(data)
    df.set_index('timestamp', inplace=True)
    return df


def _df_to_bars(df: pd.DataFrame) -> List[Bar]:
    """Convert DataFrame to list of Bar objects."""
    if 'timestamp' in df.columns:
        df = df.set_index('timestamp')
    
    bars = []
    for timestamp, row in df.iterrows():
        bar = Bar(
            timestamp=timestamp,
            open=row['open'],
            high=row['high'],
            low=row['low'],
            close=row['close'],
            volume=row['volume']
        )
        bars.append(bar)
    
    return bars


if __name__ == "__main__":
    # Test indicators
    import sys
    from datetime import datetime, timedelta
    
    # Create sample bars
    base_time = datetime(2025, 1, 2, 9, 30)
    test_bars = [
        Bar(
            timestamp=base_time + timedelta(minutes=i),
            open=100.0 + i * 0.1,
            high=100.5 + i * 0.1,
            low=99.8 + i * 0.1,
            close=100.2 + i * 0.1,
            volume=10000 + i * 100
        )
        for i in range(30)
    ]
    
    print("Testing VWAP calculation...")
    vwap_values = calculate_vwap(test_bars)
    print(f"VWAP values: {vwap_values[:5]}... (showing first 5)")
    print(f"Last VWAP: {vwap_values[-1]:.4f}")
    
    print("\nTesting ATR calculation...")
    atr_values = calculate_atr(test_bars, period=14, atr_timeframe="10min", strategy_timeframe="1min")
    print(f"ATR values: {atr_values[:5]}... (showing first 5)")
    print(f"Last ATR: {atr_values[-1]:.4f}")
    
    print("\nTesting rolling statistics...")
    deviation_history = []
    for i, bar in enumerate(test_bars):
        vwap = vwap_values[i]
        deviation = bar.close - vwap
        mean, std = update_rolling_stats(deviation_history, window=20, current_deviation=deviation)
        if i == len(test_bars) - 1:
            print(f"Final rolling mean: {mean:.4f}, std: {std:.4f}")
    
    print("\nTesting z-score calculation...")
    last_bar = test_bars[-1]
    last_vwap = vwap_values[-1]
    z_score = calculate_z_score(last_bar.close, last_vwap, mean, std)
    print(f"Z-score: {z_score:.4f}")
    
    print("\nTesting percentage deviation...")
    pct_dev = calculate_pct_deviation(last_bar.close, last_vwap)
    print(f"Percentage deviation: {pct_dev * 100:.4f}%")
    
    print("\nAll tests completed!")

