"""
Data loading and preprocessing module.

This module handles loading intraday OHLCV data from CSV files,
validating data quality, and preprocessing for backtesting.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Optional, Tuple
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Required columns for OHLCV data
REQUIRED_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]

# Alternative column name mappings (for flexibility)
COLUMN_MAPPINGS = {
    "time": "timestamp",
    "date": "timestamp",
    "datetime": "timestamp",
    "dt": "timestamp",
    "o": "open",
    "h": "high",
    "l": "low",
    "c": "close",
    "v": "volume",
    "vol": "volume",
}


def load_data(
    file_path: str,
    symbol: str,
    timestamp_col: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    max_price_move_pct: float = 5.0,
    missing_data_handling: str = "ffill",
) -> pd.DataFrame:
    """
    Load and preprocess intraday data from CSV file.
    
    IMPORTANT: timestamp_col is REQUIRED (use config.timestamp_col, never hardcode)
    
    Args:
        file_path: Path to CSV file (can be relative or absolute)
        symbol: Symbol name (for logging and error messages)
        timestamp_col: Name of timestamp column (REQUIRED - use config.timestamp_col)
        start_date: Optional start date filter (YYYY-MM-DD format)
        end_date: Optional end date filter (YYYY-MM-DD format)
        max_price_move_pct: Maximum allowed price move % in 1 minute (default: 5.0)
        missing_data_handling: How to handle missing data - "ffill", "drop", or "error" (default: "ffill")
    
    Returns:
        DataFrame with columns: timestamp, open, high, low, close, volume
        - Sorted by timestamp (ascending)
        - Timestamp converted to datetime
        - Invalid bars filtered
        - Missing values handled per missing_data_handling parameter
    
    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If required columns missing or data invalid
    """
    # Resolve file path
    resolved_path = Path(file_path).expanduser().resolve()
    
    if not resolved_path.exists():
        raise FileNotFoundError(f"Data file not found for {symbol}: {resolved_path}")
    
    logger.info(f"Loading data for {symbol} from {resolved_path}")
    
    # Read CSV file
    try:
        df = pd.read_csv(resolved_path)
    except Exception as e:
        raise ValueError(f"Error reading CSV file for {symbol}: {e}")
    
    if df.empty:
        raise ValueError(f"CSV file for {symbol} is empty")
    
    # Normalize column names (handle case-insensitive and alternative names)
    df.columns = df.columns.str.lower().str.strip()
    
    # Map alternative column names to standard names
    column_mapping = {}
    for alt_name, std_name in COLUMN_MAPPINGS.items():
        if alt_name in df.columns and std_name not in df.columns:
            column_mapping[alt_name] = std_name
    
    if column_mapping:
        df = df.rename(columns=column_mapping)
    
    # Validate timestamp column exists (NEVER hardcode, always use config.timestamp_col)
    if timestamp_col not in df.columns:
        raise ValueError(
            f"Timestamp column '{timestamp_col}' (from config) not found for {symbol}. "
            f"Available columns: {list(df.columns)}. "
            f"Update config.timestamp_col to match your data source."
        )
    
    # Validate required columns exist
    missing_cols = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing_cols:
        raise ValueError(
            f"Missing required columns for {symbol}: {missing_cols}. "
            f"Available columns: {list(df.columns)}"
        )
    
    # Convert timestamp to datetime
    try:
        df["timestamp"] = pd.to_datetime(df[timestamp_col], errors="coerce")
    except Exception as e:
        raise ValueError(f"Error converting timestamp column for {symbol}: {e}")
    
    # Check for failed timestamp conversions
    null_timestamps = df["timestamp"].isna().sum()
    if null_timestamps > 0:
        logger.warning(f"Found {null_timestamps} invalid timestamps for {symbol}, dropping rows")
        df = df.dropna(subset=["timestamp"])
    
    if df.empty:
        raise ValueError(f"No valid timestamps found for {symbol}")
    
    # Convert OHLCV columns to numeric
    numeric_cols = ["open", "high", "low", "close", "volume"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    
    # Check for failed numeric conversions
    null_numeric = df[numeric_cols].isna().any(axis=1).sum()
    if null_numeric > 0:
        logger.warning(f"Found {null_numeric} rows with invalid numeric values for {symbol}, dropping")
        df = df.dropna(subset=numeric_cols)
    
    if df.empty:
        raise ValueError(f"No valid numeric data found for {symbol}")
    
    # Sort by timestamp
    df = df.sort_values("timestamp").reset_index(drop=True)
    
    # Filter by date range if provided
    if start_date:
        start_dt = pd.to_datetime(start_date)
        df = df[df["timestamp"] >= start_dt]
        logger.info(f"Filtered to start date: {start_date}")
    
    if end_date:
        end_dt = pd.to_datetime(end_date)
        df = df[df["timestamp"] <= end_dt]
        logger.info(f"Filtered to end date: {end_date}")
    
    if df.empty:
        raise ValueError(f"No data in date range for {symbol}")
    
    # Filter invalid bars
    initial_count = len(df)
    df = _filter_invalid_bars(df, symbol, max_price_move_pct)
    filtered_count = initial_count - len(df)
    
    if filtered_count > 0:
        logger.info(f"Filtered {filtered_count} invalid bars for {symbol}")
    
    # Handle missing values based on config
    if missing_data_handling not in ["ffill", "drop", "error"]:
        raise ValueError(
            f"Invalid missing_data_handling: {missing_data_handling}. "
            f"Must be 'ffill', 'drop', or 'error'"
        )
    
    df = _handle_missing_values(df, symbol, missing_data_handling)
    
    # Validate data quality
    _validate_data_quality(df, symbol)
    
    # Select and reorder columns
    df = df[REQUIRED_COLUMNS].copy()
    
    # Detect and log timestamp gaps
    _detect_timestamp_gaps(df, symbol)
    
    logger.info(f"Loaded {len(df)} bars for {symbol} from {df['timestamp'].min()} to {df['timestamp'].max()}")
    
    return df


def _filter_invalid_bars(df: pd.DataFrame, symbol: str, max_price_move_pct: float) -> pd.DataFrame:
    """
    Filter out invalid bars based on data quality rules.
    
    Filters:
    - Zero or negative volume
    - Zero or negative prices
    - Invalid OHLC relationships (high < low, close outside range, etc.)
    - Unrealistic price moves (>max_price_move_pct% in 1 minute)
    """
    original_count = len(df)
    
    # Filter zero or negative volume
    df = df[df["volume"] > 0].copy()
    
    # Filter zero or negative prices
    price_cols = ["open", "high", "low", "close"]
    df = df[(df[price_cols] > 0).all(axis=1)].copy()
    
    # Validate OHLC relationships
    # High must be >= Low
    df = df[df["high"] >= df["low"]].copy()
    
    # Close must be between Low and High
    df = df[(df["close"] >= df["low"]) & (df["close"] <= df["high"])].copy()
    
    # Open must be between Low and High
    df = df[(df["open"] >= df["low"]) & (df["open"] <= df["high"])].copy()
    
    # Filter unrealistic price moves
    # Calculate price change percentage from previous bar
    df["price_change_pct"] = df["close"].pct_change().abs() * 100
    
    # Filter bars with >max_price_move_pct% move
    # Allow first bar (no previous bar to compare)
    if len(df) > 1:
        mask = (df["price_change_pct"] <= max_price_move_pct) | (df["price_change_pct"].isna())
        df = df[mask].copy()
        df = df.drop(columns=["price_change_pct"])
    
    filtered = original_count - len(df)
    if filtered > 0:
        logger.debug(f"Filtered {filtered} invalid bars for {symbol}")
    
    return df


def _handle_missing_values(
    df: pd.DataFrame, symbol: str, missing_data_handling: str = "ffill"
) -> pd.DataFrame:
    """
    Handle missing values in the DataFrame based on missing_data_handling mode.
    
    Args:
        df: DataFrame to process
        symbol: Symbol name (for logging)
        missing_data_handling: "ffill", "drop", or "error"
    
    Returns:
        DataFrame with missing values handled
    
    Raises:
        ValueError: If missing_data_handling is "error" and missing values found
    """
    original_count = len(df)
    
    # Check for missing values
    price_cols = ["open", "high", "low", "close"]
    has_missing_prices = df[price_cols].isna().any().any()
    has_missing_volume = df["volume"].isna().any()
    
    if not (has_missing_prices or has_missing_volume):
        return df  # No missing values, return as-is
    
    # Handle based on mode
    if missing_data_handling == "error":
        # Raise error if any missing values found
        missing_info = []
        if has_missing_prices:
            missing_info.append("prices")
        if has_missing_volume:
            missing_info.append("volume")
        raise ValueError(
            f"Missing data found for {symbol}: {', '.join(missing_info)}. "
            f"Set missing_data_handling to 'ffill' or 'drop' to handle automatically."
        )
    
    elif missing_data_handling == "drop":
        # Drop all rows with any missing values
        df = df.dropna(subset=price_cols + ["volume"]).copy()
        dropped = original_count - len(df)
        if dropped > 0:
            logger.warning(f"Dropped {dropped} rows with missing values for {symbol}")
    
    elif missing_data_handling == "ffill":
        # Forward fill prices, drop missing volume
        # Drop rows with missing volume (volume is critical and can't be forward-filled)
        df = df.dropna(subset=["volume"]).copy()
        
        # Forward fill prices (if a price is missing, use previous bar's close)
        df[price_cols] = df[price_cols].ffill()
        
        # Drop any remaining rows with missing prices (if first bar has missing prices)
        df = df.dropna(subset=price_cols).copy()
        
        dropped = original_count - len(df)
        if dropped > 0:
            logger.warning(
                f"Forward-filled missing prices and dropped {dropped} rows with missing volume for {symbol}"
            )
    
    return df


def _validate_data_quality(df: pd.DataFrame, symbol: str) -> None:
    """
    Perform final data quality validation.
    
    Raises:
        ValueError: If data quality issues are detected
    """
    if df.empty:
        raise ValueError(f"DataFrame is empty for {symbol} after preprocessing")
    
    # Check for duplicate timestamps
    duplicates = df["timestamp"].duplicated().sum()
    if duplicates > 0:
        logger.warning(f"Found {duplicates} duplicate timestamps for {symbol}, keeping first occurrence")
        df.drop_duplicates(subset=["timestamp"], keep="first", inplace=True)
    
    # Check for negative values
    if (df[["open", "high", "low", "close", "volume"]] < 0).any().any():
        raise ValueError(f"Found negative values in data for {symbol}")
    
    # Check timestamp is sorted
    if not df["timestamp"].is_monotonic_increasing:
        raise ValueError(f"Timestamps are not sorted for {symbol}")
    
    # Check for reasonable data ranges
    if df["volume"].max() > 1e12:  # Unrealistic volume
        logger.warning(f"Very large volume values detected for {symbol}, may indicate data issue")
    
    if df["close"].max() / df["close"].min() > 1000:  # >1000x price range
        logger.warning(f"Very large price range detected for {symbol}, may indicate data issue")


def _detect_timestamp_gaps(df: pd.DataFrame, symbol: str) -> None:
    """
    Detect and log timestamp gaps in the data.
    
    This helps identify missing bars or data quality issues.
    """
    if len(df) < 2:
        return
    
    # Calculate time differences between consecutive bars
    time_diffs = df["timestamp"].diff().dropna()
    
    # Expected timeframe (infer from most common interval)
    if len(time_diffs) > 0:
        most_common_diff = time_diffs.mode()[0] if len(time_diffs.mode()) > 0 else time_diffs.median()
        
        # Find gaps significantly larger than expected
        gap_threshold = most_common_diff * 3  # 3x the expected interval
        large_gaps = time_diffs[time_diffs > gap_threshold]
        
        if len(large_gaps) > 0:
            logger.warning(
                f"Found {len(large_gaps)} large timestamp gaps for {symbol}. "
                f"Largest gap: {large_gaps.max()}"
            )


def load_multiple_symbols(
    data_dir: str,
    symbols: list,
    timestamp_col: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    max_price_move_pct: float = 5.0,
    missing_data_handling: str = "ffill",
) -> dict:
    """
    Load data for multiple symbols.
    
    Args:
        data_dir: Directory containing CSV files
        symbols: List of symbols to load
        timestamp_col: Name of timestamp column (REQUIRED - use config.timestamp_col)
        start_date: Optional start date filter (YYYY-MM-DD format)
        end_date: Optional end date filter (YYYY-MM-DD format)
        max_price_move_pct: Maximum allowed price move % in 1 minute
        missing_data_handling: How to handle missing data - "ffill", "drop", or "error"
    
    Returns:
        Dictionary mapping symbol to DataFrame: {symbol: df}
    """
    data_dir_path = Path(data_dir).expanduser().resolve()
    
    if not data_dir_path.exists():
        raise FileNotFoundError(f"Data directory not found: {data_dir_path}")
    
    data_dict = {}
    
    for symbol in symbols:
        file_path = data_dir_path / f"{symbol}.csv"
        
        try:
            df = load_data(
                str(file_path),
                symbol,
                timestamp_col=timestamp_col,
                start_date=start_date,
                end_date=end_date,
                max_price_move_pct=max_price_move_pct,
                missing_data_handling=missing_data_handling,
            )
            data_dict[symbol] = df
        except Exception as e:
            logger.error(f"Failed to load data for {symbol}: {e}")
            raise
    
    return data_dict


def load_bars(
    symbol: str,
    data_dir: str,
    timeframe: str,
    timestamp_col: str = "timestamp",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> list:
    """
    Load bars as a list of Bar objects for backtesting.
    
    This is a convenience wrapper around load_data() that returns
    Bar objects instead of a DataFrame.
    
    Args:
        symbol: Symbol to load
        data_dir: Directory containing CSV files
        timeframe: Timeframe (e.g., "1min", "5min")
        timestamp_col: Name of timestamp column
        start_date: Optional start date filter
        end_date: Optional end date filter
    
    Returns:
        List of Bar objects
    
    Raises:
        FileNotFoundError: If data file not found
        ValueError: If data invalid
    """
    from .indicators import Bar
    
    # Construct file path
    data_path = Path(data_dir)
    file_path = data_path / f"{symbol}_{timeframe}.csv"
    
    if not file_path.exists():
        # Try without timeframe
        file_path = data_path / f"{symbol}.csv"
        if not file_path.exists():
            raise FileNotFoundError(
                f"Data file not found: {data_path}/{symbol}_{timeframe}.csv or {data_path}/{symbol}.csv"
            )
    
    # Load DataFrame
    df = load_data(
        file_path=str(file_path),
        symbol=symbol,
        timestamp_col=timestamp_col,
        start_date=start_date,
        end_date=end_date
    )
    
    # Convert to Bar objects
    bars = []
    for _, row in df.iterrows():
        bar = Bar(
            timestamp=row['timestamp'],
            open=row['open'],
            high=row['high'],
            low=row['low'],
            close=row['close'],
            volume=row['volume']
        )
        bars.append(bar)
    
    return bars


if __name__ == "__main__":
    # Test data loading
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python data_loader.py <csv_file_path> [symbol]")
        sys.exit(1)
    
    file_path = sys.argv[1]
    symbol = sys.argv[2] if len(sys.argv) > 2 else "TEST"
    
    try:
        df = load_data(file_path, symbol)
        print(f"\n✅ Successfully loaded {len(df)} bars for {symbol}")
        print(f"\nFirst 5 rows:")
        print(df.head())
        print(f"\nLast 5 rows:")
        print(df.tail())
        print(f"\nData summary:")
        print(df.describe())
        print(f"\nDate range: {df['timestamp'].min()} to {df['timestamp'].max()}")
    except Exception as e:
        print(f"❌ Error loading data: {e}")
        sys.exit(1)

