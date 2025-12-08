"""
Main backtesting engine for VWAP Mean Reversion Strategy.

This module orchestrates the complete backtesting process:
1. Load historical data
2. Calculate indicators (VWAP, ATR, rolling stats)
3. Generate entry/exit signals
4. Validate trades via risk management
5. Execute orders with realistic fills
6. Track positions and performance
7. Generate results and reports

Architecture:
    Data -> Indicators -> Signals -> Risk -> Execution -> Positions -> Results
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import json
import warnings

# Import all modules
try:
    from .config import load_config, Config
    from .data_loader import load_bars
    from .indicators import (
        Bar, 
        calculate_vwap, 
        calculate_atr,
        calculate_z_score,
        calculate_pct_deviation
    )
    from .signal_engine import (
        StrategyState,
        init_strategy_state,
        update_strategy_state,
        generate_entry_signal,
        check_exit_condition
    )
    from .positions import Position, PositionManager
    from .risk_manager import (
        calculate_stop_loss,
        calculate_position_size,
        validate_trade_risk,
        check_daily_risk_limit,
        RiskMetrics,
        generate_risk_summary
    )
    from .execution_engine import (
        Order,
        fill_market_order,
        update_position_from_fill,
        generate_execution_summary
    )
except ImportError:
    # For direct execution
    from config import load_config, Config
    from data_loader import load_bars
    from indicators import (
        Bar, 
        calculate_vwap, 
        calculate_atr,
        calculate_z_score,
        calculate_pct_deviation
    )
    from signal_engine import (
        StrategyState,
        init_strategy_state,
        update_strategy_state,
        generate_entry_signal,
        check_exit_condition
    )
    from positions import Position, PositionManager
    from risk_manager import (
        calculate_stop_loss,
        calculate_position_size,
        validate_trade_risk,
        check_daily_risk_limit,
        RiskMetrics,
        generate_risk_summary
    )
    from execution_engine import (
        Order,
        fill_market_order,
        update_position_from_fill,
        generate_execution_summary
    )


# ==========================
# Backtest Core Functions
# ==========================

def run_backtest(config: Config, verbose: bool = True) -> Dict:
    """
    Run complete backtest for VWAP mean reversion strategy.
    
    Args:
        config: Configuration object with all strategy parameters
        verbose: Print progress messages
    
    Returns:
        Dictionary containing:
            - trades: List of all trades
            - equity_curve: Daily equity values
            - performance: Performance metrics
            - positions_summary: Position statistics
            - risk_summary: Risk metrics
            - execution_summary: Execution statistics
    """
    if verbose:
        print("=" * 80)
        print("VWAP MEAN REVERSION BACKTEST")
        print("=" * 80)
        print(f"Mode: {config.mode}")
        print(f"Symbols: {config.symbols}")
        print(f"Timeframe: {config.timeframe}")
        print(f"Initial Capital: ${config.initial_capital:,.2f}")
        print(f"Signal Type: {config.signal_type}")
        print(f"Entry Threshold: {config.entry_z if config.signal_type == 'zscore' else config.entry_pct}")
        print(f"Stop Type: {config.stop_type}")
        print("-" * 80)
    
    # Initialize tracking structures
    position_manager = PositionManager(config=config, initial_capital=config.initial_capital)
    all_fills = []
    equity_curve = []
    daily_stats = []
    
    # Process each symbol
    for symbol in config.symbols:
        if verbose:
            print(f"\n{'='*80}")
            print(f"Processing Symbol: {symbol}")
            print(f"{'='*80}")
        
        # Load data
        try:
            bars = load_bars(
                symbol=symbol,
                data_dir=config.data_dir,
                timeframe=config.timeframe,
                timestamp_col=config.timestamp_col
            )
            if verbose:
                print(f"✓ Loaded {len(bars)} bars")
                print(f"  Date Range: {bars[0].timestamp} to {bars[-1].timestamp}")
        except Exception as e:
            print(f"✗ Error loading data for {symbol}: {e}")
            continue
        
        # Initialize strategy state for this symbol
        state = init_strategy_state(symbol, config)
        
        # Track current day for daily resets
        current_day = None
        
        # Main bar-by-bar loop
        for i, bar in enumerate(bars):
            bar_date = bar.timestamp.date()
            
            # Update bar index in state
            state.bar_idx = i
            
            # === DAILY RESET ===
            if current_day is None or bar_date != current_day:
                if verbose and current_day is not None:
                    # Print previous day's summary
                    if current_day in position_manager.daily_stats:
                        stats = position_manager.daily_stats[current_day]
                        if stats.trades_count > 0:
                            print(f"\n--- Day {current_day} Summary ---")
                            print(f"  Trades: {stats.trades_count} | P&L: ${stats.total_pnl:,.2f} | "
                                  f"Win Rate: {stats.win_rate:.1f}%")  # Fixed: win_rate is already a percentage
                
                # Reset for new day
                current_day = bar_date
                position_manager.reset_daily_tracking(bar.timestamp)
                state = init_strategy_state(symbol, config)
                
                if verbose:
                    print(f"\n[{bar.timestamp.date()}] New trading day started")
            
            # === UPDATE INDICATORS ===
            vwap = calculate_vwap(bars[:i+1])
            state.current_vwap = vwap
            
            # Update strategy state (rolling stats, etc.)
            update_strategy_state(state, bar, vwap, config)
            
            # Calculate current z-score and deviation
            z_score = calculate_z_score(bar.close, vwap, state.rolling_mean_deviation, state.rolling_std_deviation)
            pct_deviation = calculate_pct_deviation(bar.close, vwap)
            
            # === PERIODIC MONITORING (every 30 minutes) ===
            if verbose and i > 0 and i % 30 == 0:
                minutes_elapsed = (bar.timestamp.time().hour * 60 + bar.timestamp.time().minute)
                session_start_minutes = 9 * 60 + 30  # 9:30 AM
                if minutes_elapsed >= session_start_minutes:
                    print(f"[{bar.timestamp}] 📊 {symbol}: Price=${bar.close:.2f} | VWAP=${vwap:.2f} | "
                          f"Z-Score={z_score:.2f} | Dev={pct_deviation*100:.2f}%")
            
            # === CHECK TIME FILTERS ===
            # Skip early bars (market open)
            minutes_since_open = (bar.timestamp.time().hour * 60 + 
                                 bar.timestamp.time().minute)
            
            # Convert session_start from string "HH:MM" or int HHMM to minutes
            if isinstance(config.session_start, str):
                h, m = map(int, config.session_start.split(':'))
                session_start_minutes = h * 60 + m
            else:
                session_start_minutes = config.session_start // 100 * 60 + config.session_start % 100
            
            if minutes_since_open < session_start_minutes + config.skip_open_minutes:
                continue
            
            # Check close before end
            if isinstance(config.session_end, str):
                h, m = map(int, config.session_end.split(':'))
                session_end_minutes = h * 60 + m
            else:
                session_end_minutes = config.session_end // 100 * 60 + config.session_end % 100
            
            if minutes_since_open >= session_end_minutes - config.close_before_end_minutes:
                # Force close all positions before market close
                _force_close_positions(position_manager, symbol, bar, config, all_fills, verbose)
                continue
            
            # === CALCULATE ATR (for stop loss) ===
            atr = None
            if i >= config.stop_atr_window:
                atr = calculate_atr(bars[max(0, i-config.stop_atr_window):i+1], window=config.stop_atr_window)
            
            # === EXIT LOGIC ===
            current_position = position_manager.get_position(symbol)
            if current_position:
                # Check stop loss
                if current_position.is_stop_loss_hit(bar):
                    if verbose:
                        print(f"[{bar.timestamp}] 🛑 STOP LOSS: {symbol} @ ${bar.close:.2f} | "
                              f"VWAP: ${vwap:.2f} | Z: {z_score:.2f}")
                    _close_position(position_manager, current_position, bar, config, 
                                   all_fills, "stop_loss", verbose)
                    continue
                
                # Check max holding time
                holding_time = (bar.timestamp - current_position.entry_time).total_seconds() / 60
                if holding_time >= config.max_holding_minutes:
                    if verbose:
                        print(f"[{bar.timestamp}] ⏱️  MAX HOLD TIME: {symbol} @ ${bar.close:.2f} | "
                              f"VWAP: ${vwap:.2f} | Z: {z_score:.2f}")
                    _close_position(position_manager, current_position, bar, config, 
                                   all_fills, "max_hold_time", verbose)
                    continue
                
                # Check exit signal
                should_exit, exit_reason = check_exit_condition(
                    position=current_position,
                    bar=bar,
                    vwap=vwap,
                    rolling_mean=state.rolling_mean_deviation,
                    rolling_std=state.rolling_std_deviation,
                    config=config
                )
                
                if should_exit:
                    if verbose:
                        print(f"[{bar.timestamp}] 🔴 EXIT ({exit_reason}): {symbol} @ ${bar.close:.2f} | "
                              f"VWAP: ${vwap:.2f} | Z: {z_score:.2f}")
                    _close_position(position_manager, current_position, bar, config, 
                                   all_fills, exit_reason, verbose)
                    continue
            
            # === ENTRY LOGIC ===
            if not current_position:
                # Check daily loss limit
                can_trade, _ = check_daily_risk_limit(
                    position_manager.daily_pnl, 
                    config.initial_capital,
                    config.daily_loss_limit_pct
                )
                if not can_trade:
                    if verbose and position_manager.daily_pnl < 0:
                        print(f"[{bar.timestamp}] Daily loss limit reached: ${position_manager.daily_pnl:,.2f}")
                    continue
                
                # Generate entry signal
                # z-score and pct_deviation already calculated above in monitoring section
                entry_signal = generate_entry_signal(
                    bar=bar,
                    vwap=vwap,
                    z_score=z_score,
                    pct_deviation=pct_deviation,
                    config=config,
                    state=state,
                    position_manager=position_manager
                )
                
                if entry_signal:
                    # entry_signal is a string: "LONG" or "SHORT"
                    direction = entry_signal
                    
                    # Calculate stop loss
                    stop_loss = calculate_stop_loss(
                        entry_price=bar.close,
                        direction=direction,
                        config=config,
                        atr=atr
                    )
                    
                    # Calculate position size
                    position_size = calculate_position_size(
                        entry_price=bar.close,
                        stop_loss=stop_loss,
                        direction=direction,
                        capital=position_manager.current_capital,
                        max_risk_pct=config.max_position_risk_pct
                    )
                    
                    # Validate trade risk (target is VWAP for mean reversion)
                    is_valid, reason = validate_trade_risk(
                        entry_price=bar.close,
                        stop_loss=stop_loss,
                        target_price=vwap,
                        direction=direction,
                        config=config
                    )
                    
                    if not is_valid:
                        if verbose:
                            print(f"[{bar.timestamp}] Trade rejected: {reason}")
                        continue
                    
                    # Check if position can be opened
                    can_open, msg = position_manager.can_open_position(symbol)
                    if not can_open:
                        if verbose:
                            print(f"[{bar.timestamp}] Cannot open position: {msg}")
                        continue
                    
                    # Execute entry order
                    order = Order(
                        symbol=symbol,
                        direction=direction,
                        order_type="MARKET",
                        size=position_size,
                        timestamp=bar.timestamp
                    )
                    
                    fill = fill_market_order(order, bar, config)
                    all_fills.append(fill)
                    
                    # Open position (PositionManager expects different parameters)
                    position = position_manager.open_position(
                        symbol=symbol,
                        direction=direction,
                        entry_price=fill.fill_price,
                        entry_time=bar.timestamp,
                        entry_bar_idx=state.bar_idx,
                        stop_loss=stop_loss,
                        entry_vwap=vwap,
                        entry_z=z_score,
                        size=position_size
                    )
                    
                    if verbose and position:
                        signal_type = "zscore" if config.signal_type == 'zscore' else "pct"
                        print(f"[{bar.timestamp}] 🟢 ENTRY: {direction} {symbol} "
                              f"@ ${fill.fill_price:.2f} | Size: {position_size} | "
                              f"Stop: ${stop_loss:.2f} | VWAP: ${vwap:.2f} | Z: {z_score:.2f}")
            
            # === TRACK EQUITY ===
            # Calculate current equity (cash + open positions)
            equity = position_manager.current_capital
            for symbol_positions in position_manager.open_positions.values():
                for pos in symbol_positions:
                    unrealized = pos.unrealized_pnl(bar.close)
                    equity += unrealized
            
            equity_curve.append({
                'timestamp': bar.timestamp,
                'equity': equity,
                'cash': position_manager.current_capital,
                'open_positions': len(position_manager.open_positions)
            })
    
    if verbose:
        print(f"\n{'='*80}")
        print("BACKTEST COMPLETE")
        print("=" * 80)
    
    # === GENERATE RESULTS ===
    results = _generate_results(
        position_manager=position_manager,
        equity_curve=equity_curve,
        all_fills=all_fills,
        config=config,
        verbose=verbose
    )
    
    # === SAVE RESULTS ===
    if config.save_trades or config.save_equity_curve:
        _save_results(results, config, verbose)
    
    return results


def _force_close_positions(
    position_manager: PositionManager,
    symbol: str,
    bar: Bar,
    config: Config,
    all_fills: List,
    verbose: bool
):
    """Force close all positions before market close."""
    position = position_manager.get_position(symbol)
    if position:
        _close_position(position_manager, position, bar, config, all_fills, 
                       "eod_close", verbose)


def _close_position(
    position_manager: PositionManager,
    position: Position,
    bar: Bar,
    config: Config,
    all_fills: List,
    reason: str,
    verbose: bool
):
    """Close a position and record fill."""
    # Create close order
    order = Order(
        symbol=position.symbol,
        direction="SHORT" if position.direction == "LONG" else "LONG",
        order_type="MARKET",
        size=position.size,
        timestamp=bar.timestamp
    )
    
    # Execute fill
    fill = fill_market_order(order, bar, config)
    all_fills.append(fill)
    
    # Close position
    pnl = position_manager.close_position(
        position=position,
        exit_price=fill.fill_price,
        exit_time=bar.timestamp,
        exit_reason=reason,
        commission=fill.commission,
        slippage=fill.slippage
    )
    
    if verbose:
        print(f"  → Closed @ ${fill.fill_price:.2f} | P&L: ${pnl:,.2f}")


def _generate_results(
    position_manager: PositionManager,
    equity_curve: List[Dict],
    all_fills: List,
    config: Config,
    verbose: bool
) -> Dict:
    """Generate comprehensive results dictionary."""
    
    # Get performance summary
    perf = position_manager.get_performance_summary()
    
    # Convert equity curve to DataFrame
    equity_df = pd.DataFrame(equity_curve)
    
    # Calculate returns
    equity_df['returns'] = equity_df['equity'].pct_change()
    
    # Calculate risk metrics
    returns = equity_df['returns'].dropna()
    risk_metrics = {}
    
    if len(returns) > 0 and len(equity_df) > 0:
        max_dd, peak_idx, trough_idx = RiskMetrics.calculate_max_drawdown(equity_df['equity'].values)
        total_return_pct = ((equity_df['equity'].iloc[-1] / config.initial_capital) - 1) * 100
        
        risk_metrics['max_drawdown'] = max_dd
        risk_metrics['sharpe_ratio'] = RiskMetrics.calculate_sharpe_ratio(returns.values)
        risk_metrics['sortino_ratio'] = RiskMetrics.calculate_sortino_ratio(returns.values)
        risk_metrics['calmar_ratio'] = RiskMetrics.calculate_calmar_ratio(total_return_pct, max_dd)
    
    # Get all trades
    trades_df = position_manager.export_trades()
    
    # Convert Position objects to dicts for risk_summary
    trades_dicts = []
    for pos in position_manager.closed_positions:
        trades_dicts.append({
            'entry_price': pos.entry_price,
            'exit_price': pos.exit_price,
            'stop_loss': pos.stop_loss,
            'size': pos.size,
            'realized_pnl': pos.realized_pnl,
            'direction': pos.direction
        })
    
    # Generate summaries
    risk_summary = generate_risk_summary(
        trades=trades_dicts,
        equity_curve=equity_df['equity'].values.tolist(),
        initial_capital=config.initial_capital,
        config=config
    )
    exec_summary = generate_execution_summary(all_fills)
    
    results = {
        'config': {
            'symbols': config.symbols,
            'timeframe': config.timeframe,
            'initial_capital': config.initial_capital,
            'signal_type': config.signal_type,
            'entry_threshold': config.entry_z if config.signal_type == 'zscore' else config.entry_pct,
            'stop_type': config.stop_type
        },
        'performance': {
            **perf,
            **risk_metrics
        },
        'trades': trades_df,
        'equity_curve': equity_df,
        'risk_summary': risk_summary,
        'execution_summary': exec_summary
    }
    
    if verbose:
        _print_results_summary(results)
    
    return results


def _print_results_summary(results: Dict):
    """Print formatted results summary."""
    perf = results['performance']
    
    print("\n" + "=" * 80)
    print("PERFORMANCE SUMMARY")
    print("=" * 80)
    
    print(f"\n📊 Trading Statistics:")
    print(f"  Total Trades:       {perf['total_trades']}")
    print(f"  Winning Trades:     {perf['winning_trades']}")
    print(f"  Losing Trades:      {perf['losing_trades']}")
    print(f"  Win Rate:           {perf['win_rate']:.2f}%")  # Fixed: win_rate is already a percentage
    
    print(f"\n💰 Profit & Loss:")
    print(f"  Total P&L:          ${perf['total_pnl']:,.2f}")
    print(f"  Gross Profit:       ${perf['gross_profit']:,.2f}")
    print(f"  Gross Loss:         ${perf['gross_loss']:,.2f}")
    print(f"  Profit Factor:      {perf['profit_factor']:.2f}")
    print(f"  Average Win:        ${perf['avg_win']:,.2f}")
    print(f"  Average Loss:       ${perf['avg_loss']:,.2f}")
    
    print(f"\n📈 Returns:")
    print(f"  Final Capital:      ${perf['final_capital']:,.2f}")
    print(f"  Total Return:       {perf['total_return']:.2%}")
    
    print(f"\n⚠️ Risk Metrics:")
    print(f"  Max Drawdown:       {perf.get('max_drawdown', 0):.2%}")
    print(f"  Sharpe Ratio:       {perf.get('sharpe_ratio', 0):.2f}")
    print(f"  Sortino Ratio:      {perf.get('sortino_ratio', 0):.2f}")
    print(f"  Calmar Ratio:       {perf.get('calmar_ratio', 0):.2f}")
    
    if 'execution_summary' in results:
        exec_sum = results['execution_summary']
        print(f"\n🔄 Execution:")
        print(f"  Total Fills:        {exec_sum['total_fills']}")
        print(f"  Avg Slippage:       ${exec_sum['avg_slippage_dollars']:.2f}")
        print(f"  Total Commission:   ${exec_sum['total_commission']:.2f}")
        print(f"  Total Costs:        ${exec_sum['total_costs']:.2f}")


def _save_results(results: Dict, config: Config, verbose: bool):
    """Save results to files."""
    results_dir = Path(config.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Save trades
    if config.save_trades and len(results['trades']) > 0:
        trades_path = results_dir / f"trades_{timestamp}.csv"
        results['trades'].to_csv(trades_path, index=False)
        if verbose:
            print(f"\n✓ Saved trades to: {trades_path}")
    
    # Save equity curve
    if config.save_equity_curve and len(results['equity_curve']) > 0:
        equity_path = results_dir / f"equity_curve_{timestamp}.csv"
        results['equity_curve'].to_csv(equity_path, index=False)
        if verbose:
            print(f"✓ Saved equity curve to: {equity_path}")
    
    # Save performance summary
    perf_path = results_dir / f"performance_{timestamp}.json"
    
    # Convert to JSON-serializable format
    perf_json = {
        'config': results['config'],
        'performance': results['performance'],
        'risk_summary': results['risk_summary'],
        'execution_summary': results['execution_summary']
    }
    
    with open(perf_path, 'w') as f:
        json.dump(perf_json, f, indent=2, default=str)
    
    if verbose:
        print(f"✓ Saved performance summary to: {perf_path}")


# ==========================
# Main Entry Point
# ==========================

def main():
    """Main entry point for backtesting."""
    import argparse
    
    parser = argparse.ArgumentParser(description='VWAP Mean Reversion Backtest')
    parser.add_argument('config', type=str, help='Path to config YAML file')
    parser.add_argument('--verbose', action='store_true', help='Print verbose output')
    parser.add_argument('--quiet', action='store_true', help='Suppress all output')
    
    args = parser.parse_args()
    
    # Load configuration
    try:
        config = load_config(args.config)
    except Exception as e:
        print(f"Error loading config: {e}")
        return
    
    # Run backtest
    verbose = args.verbose and not args.quiet
    
    try:
        results = run_backtest(config, verbose=verbose)
        
        if not args.quiet:
            print(f"\n{'='*80}")
            print("✓ Backtest completed successfully")
            print("=" * 80)
        
        return results
        
    except Exception as e:
        print(f"\n✗ Backtest failed: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    main()
