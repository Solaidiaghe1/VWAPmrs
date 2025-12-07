"""
Configuration loading and validation module.

This module handles loading and validating the strategy configuration from YAML files.
All configuration parameters are flattened (no nested structure).
Returns a dot-accessible Config object for cleaner code.
"""

import yaml
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict


class Config(SimpleNamespace):
    """
    Dot-accessible configuration object.
    
    Usage:
        config = load_config("config.yaml")
        entry_z = config.entry_z  # Instead of config['entry_z']
    """
    pass


# LEVEL 1: Required keys (mandatory)
REQUIRED_KEYS = [
    "mode",
    "symbols",
    "timeframe",
    "entry_z",
    "exit_z",
    "initial_capital",
    "max_position_risk_pct",
    "stop_atr_mult",
    "data_dir",
    "results_dir",
    "session_start",
    "session_end",
    "signal_type",
    "rolling_window",
    "cooldown_bars",
    "skip_open_minutes",
    "close_before_end_minutes",
    "daily_loss_limit_pct",
    "max_positions_per_symbol",
    "max_total_positions",
    "max_holding_minutes",
    "stop_type",
    "stop_atr_window",
    "atr_timeframe",
    "fixed_stop_pct",
    "slippage_model",
    "slippage_bps",
    "commission_per_trade",
    "volume_participation_limit_pct",
    "timestamp_col",
]

# Minimal defaults (only for truly optional parameters)
DEFAULTS = {
    "mode": "backtest",
    "save_trades": True,
    "save_equity_curve": True,
}


def load_config(config_path: str) -> Config:
    """
    Load and validate configuration from YAML file.
    
    IMPORTANT: 
    - config_path is REQUIRED (never hardcoded)
    - Accepts relative paths, resolves to absolute internally
    - Returns dot-accessible Config object: config.entry_z (not config['entry_z'])
    
    Args:
        config_path: Path to YAML config file (required, can be relative or absolute)
    
    Returns:
        Config object with dot-accessible attributes
    
    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If required parameters missing, wrong type, or invalid range
    """
    # Resolve path: accept relative, convert to absolute
    resolved_path = Path(config_path).expanduser().resolve()
    
    # Check if file exists
    if not resolved_path.exists():
        raise FileNotFoundError(f"Config file not found: {resolved_path}")
    
    # Load YAML file
    with open(resolved_path, "r") as f:
        raw_config = yaml.safe_load(f)
    
    # Handle both nested and flat formats for backward compatibility
    if raw_config is None:
        raise ValueError("Config file is empty or invalid")
    
    if 'strategy' in raw_config:
        config_dict = raw_config['strategy']
    else:
        config_dict = raw_config
    
    # Apply minimal defaults
    for key, value in DEFAULTS.items():
        config_dict.setdefault(key, value)
    
    # LEVEL 1: Validate required keys
    missing_keys = [key for key in REQUIRED_KEYS if key not in config_dict]
    if missing_keys:
        raise ValueError(f"Missing required parameters: {', '.join(missing_keys)}")
    
    # LEVEL 2: Type validation
    type_checks = {
        "mode": str,
        "symbols": list,
        "timeframe": str,
        "entry_z": (int, float),
        "exit_z": (int, float),
        "entry_pct": (int, float),
        "exit_pct": (int, float),
        "initial_capital": (int, float),
        "max_position_risk_pct": (int, float),
        "daily_loss_limit_pct": (int, float),
        "rolling_window": int,
        "cooldown_bars": int,
        "skip_open_minutes": int,
        "close_before_end_minutes": int,
        "max_holding_minutes": int,
        "max_positions_per_symbol": int,
        "max_total_positions": int,
        "stop_atr_window": int,
        "stop_atr_mult": (int, float),
        "fixed_stop_pct": (int, float),
        "slippage_bps": (int, float),
        "commission_per_trade": (int, float),
        "volume_participation_limit_pct": (int, float),
        "save_trades": bool,
        "save_equity_curve": bool,
    }
    
    for key, expected_type in type_checks.items():
        if key in config_dict:
            if not isinstance(config_dict[key], expected_type):
                raise ValueError(
                    f"Invalid type for '{key}': expected {expected_type.__name__ if not isinstance(expected_type, tuple) else ' or '.join(t.__name__ for t in expected_type)}, "
                    f"got {type(config_dict[key]).__name__}"
                )
    
    # Validate list contents
    if not isinstance(config_dict["symbols"], list) or len(config_dict["symbols"]) == 0:
        raise ValueError("'symbols' must be a non-empty list")
    
    for symbol in config_dict["symbols"]:
        if not isinstance(symbol, str):
            raise ValueError(f"All symbols must be strings, got {type(symbol).__name__}: {symbol}")
    
    # LEVEL 3: Range validation
    # Signal type validation
    if config_dict["signal_type"] not in ["zscore", "pct"]:
        raise ValueError(f"Invalid signal_type: {config_dict['signal_type']}. Must be 'zscore' or 'pct'")
    
    # Stop type validation
    if config_dict["stop_type"] not in ["atr", "fixed"]:
        raise ValueError(f"Invalid stop_type: {config_dict['stop_type']}. Must be 'atr' or 'fixed'")
    
    # Slippage model validation
    if config_dict["slippage_model"] not in ["bps", "volume"]:
        raise ValueError(f"Invalid slippage_model: {config_dict['slippage_model']}. Must be 'bps' or 'volume'")
    
    # Mode validation
    if config_dict["mode"] not in ["backtest", "paper", "live"]:
        raise ValueError(f"Invalid mode: {config_dict['mode']}. Must be 'backtest', 'paper', or 'live'")
    
    # Numeric range validations
    if config_dict["entry_z"] <= 0 or config_dict["entry_z"] > 10:
        raise ValueError(f"entry_z must be between 0 and 10, got {config_dict['entry_z']}")
    
    if config_dict["exit_z"] < 0 or config_dict["exit_z"] > 5:
        raise ValueError(f"exit_z must be between 0 and 5, got {config_dict['exit_z']}")
    
    if config_dict["max_position_risk_pct"] <= 0 or config_dict["max_position_risk_pct"] > 5:
        raise ValueError(
            f"max_position_risk_pct must be between 0 and 5 (safety limit), got {config_dict['max_position_risk_pct']}"
        )
    
    if config_dict["daily_loss_limit_pct"] <= 0 or config_dict["daily_loss_limit_pct"] > 100:
        raise ValueError(
            f"daily_loss_limit_pct must be between 0 and 100, got {config_dict['daily_loss_limit_pct']}"
        )
    
    if config_dict["rolling_window"] < 10 or config_dict["rolling_window"] > 200:
        raise ValueError(f"rolling_window must be between 10 and 200, got {config_dict['rolling_window']}")
    
    if config_dict["cooldown_bars"] < 0 or config_dict["cooldown_bars"] > 100:
        raise ValueError(f"cooldown_bars must be between 0 and 100, got {config_dict['cooldown_bars']}")
    
    if config_dict["max_holding_minutes"] <= 0 or config_dict["max_holding_minutes"] > 1440:
        raise ValueError(
            f"max_holding_minutes must be between 0 and 1440 (24 hours), got {config_dict['max_holding_minutes']}"
        )
    
    if config_dict["stop_atr_mult"] <= 0 or config_dict["stop_atr_mult"] > 10:
        raise ValueError(f"stop_atr_mult must be between 0 and 10, got {config_dict['stop_atr_mult']}")
    
    if config_dict["stop_atr_window"] < 5 or config_dict["stop_atr_window"] > 50:
        raise ValueError(f"stop_atr_window must be between 5 and 50, got {config_dict['stop_atr_window']}")
    
    if config_dict["slippage_bps"] < 0 or config_dict["slippage_bps"] > 100:
        raise ValueError(f"slippage_bps must be between 0 and 100, got {config_dict['slippage_bps']}")
    
    if config_dict["volume_participation_limit_pct"] <= 0 or config_dict["volume_participation_limit_pct"] > 50:
        raise ValueError(
            f"volume_participation_limit_pct must be between 0 and 50, got {config_dict['volume_participation_limit_pct']}"
        )
    
    if config_dict["initial_capital"] <= 0:
        raise ValueError(f"initial_capital must be positive, got {config_dict['initial_capital']}")
    
    # Convert to dot-accessible Config object
    config = Config(**config_dict)
    
    return config


if __name__ == "__main__":
    # Test loading config
    import sys
    
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    
    try:
        config = load_config(config_path)
        print("✅ Config loaded successfully!")
        print(f"Mode: {config.mode}")
        print(f"Symbols: {config.symbols}")
        print(f"Timeframe: {config.timeframe}")
        print(f"Signal type: {config.signal_type}")
        print(f"Initial capital: ${config.initial_capital:,.2f}")
        print(f"Entry Z: {config.entry_z}")
        print(f"Exit Z: {config.exit_z}")
    except Exception as e:
        print(f"❌ Error loading config: {e}")
        sys.exit(1)

