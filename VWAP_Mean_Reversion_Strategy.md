# Intraday VWAP Mean Reversion Strategy

## Overview

The Intraday VWAP Mean Reversion Strategy is a quantitative trading approach that exploits temporary price deviations from the Volume-Weighted Average Price (VWAP) during a trading day. The strategy assumes that prices will revert to the VWAP after significant deviations, providing profitable trading opportunities.

## What is VWAP?

**Volume-Weighted Average Price (VWAP)** is a trading benchmark that gives the average price a security has traded at throughout the day, based on both volume and price. It is calculated as:

```
VWAP = Σ(Price × Volume) / Σ(Volume)
```

### Key Characteristics:
- **Intraday Metric**: VWAP resets each trading day
- **Volume-Weighted**: Places more weight on prices with higher trading volume
- **Reference Point**: Acts as a fair value indicator for the day
- **Dynamic**: Updates throughout the trading session

## Mean Reversion Concept

Mean reversion is the theory that prices and returns eventually move back toward their mean or average. In this strategy:
- **Mean**: The VWAP line
- **Deviation**: Price moves away from VWAP
- **Reversion**: Price returns toward VWAP

### Why Mean Reversion Works:
1. **Market Efficiency**: Temporary inefficiencies create opportunities
2. **Liquidity**: Large deviations attract counter-trend traders
3. **Institutional Behavior**: Institutions often trade around VWAP
4. **Psychological Levels**: VWAP serves as a psychological anchor

## Strategy Logic

### Core Principle
When price deviates significantly from VWAP, it's likely to revert back. The strategy:
1. **Identifies** significant deviations from VWAP
2. **Enters** positions betting on reversion
3. **Exits** when price returns to VWAP or reaches profit targets

### Deviation Measurement

Price deviation from VWAP can be measured as:
- **Absolute Deviation**: `|Price - VWAP|`
- **Percentage Deviation**: `(Price - VWAP) / VWAP × 100`
- **Standard Deviation**: `(Price - VWAP) / σ(VWAP)`

## Entry Rules

### Long Entry (Buy Signal)
- Price falls **below** VWAP by a threshold (e.g., 0.5-2%)
- Volume confirms the move (optional filter)
- Price shows signs of stabilization or reversal
- Time-based filters (avoid late-day entries)

### Short Entry (Sell Signal)
- Price rises **above** VWAP by a threshold (e.g., 0.5-2%)
- Volume confirms the move (optional filter)
- Price shows signs of exhaustion or reversal
- Time-based filters (avoid late-day entries)

### Entry Thresholds
- **Conservative**: 1.5-2% deviation
- **Moderate**: 0.75-1.5% deviation
- **Aggressive**: 0.5-0.75% deviation

## Exit Rules

### Profit Targets
1. **Primary Target**: Price returns to VWAP
2. **Secondary Target**: 50% of deviation recovered
3. **Extended Target**: Price crosses VWAP (momentum continuation)

### Stop Loss
1. **Fixed Stop**: 0.5-1% from entry price
2. **ATR-Based Stop**: 1-2× Average True Range
3. **Deviation-Based Stop**: Stop if deviation increases by 50%

### Time-Based Exits
- Exit all positions before market close (e.g., 15-30 minutes before)
- Exit if position held beyond maximum holding period (e.g., 2-4 hours)

## Risk Management

### Position Sizing
- **Fixed Dollar Amount**: Risk fixed dollar amount per trade
- **Percentage of Capital**: Risk 0.5-2% of account per trade
- **Volatility-Adjusted**: Adjust size based on ATR or volatility

### Maximum Exposure
- Limit number of concurrent positions
- Set maximum daily loss limit
- Implement position concentration limits

### Risk Metrics
- **Risk-Reward Ratio**: Minimum 1:1, target 1:2 or better
- **Win Rate**: Target 50-60%+ win rate
- **Sharpe Ratio**: Monitor risk-adjusted returns

## Implementation Considerations

### Data Requirements
- **Real-time or Intraday Data**: 1-minute, 5-minute, or tick data
- **Volume Data**: Essential for VWAP calculation
- **Historical Data**: For backtesting and parameter optimization

### VWAP Calculation
```python
# Pseudocode for VWAP calculation
def calculate_vwap(prices, volumes, start_time):
    cumulative_price_volume = 0
    cumulative_volume = 0
    vwap_values = []
    
    for i in range(len(prices)):
        cumulative_price_volume += prices[i] * volumes[i]
        cumulative_volume += volumes[i]
        vwap = cumulative_price_volume / cumulative_volume
        vwap_values.append(vwap)
    
    return vwap_values
```

### Key Parameters to Optimize
1. **Deviation Threshold**: Entry trigger level
2. **Stop Loss Distance**: Risk per trade
3. **Profit Target**: Take profit level
4. **Time Filters**: Entry/exit time windows
5. **Volume Filters**: Minimum volume requirements
6. **Maximum Holding Period**: Time-based exit

## Strategy Variations

### 1. Standard Mean Reversion
- Enter when deviation exceeds threshold
- Exit when price returns to VWAP

### 2. Momentum Confirmation
- Wait for momentum indicators to confirm reversal
- Use RSI, MACD, or price action patterns

### 3. Multi-Timeframe
- Use higher timeframe VWAP for trend filter
- Use lower timeframe for entry timing

### 4. Volume-Weighted Deviation
- Consider volume profile in deviation calculation
- Weight recent volume more heavily

### 5. Statistical Mean Reversion
- Use Z-score or standard deviation bands
- Enter when price exceeds 2 standard deviations

## Best Practices

### Market Conditions
- **Works Best In**: Range-bound, choppy markets
- **Avoid In**: Strong trending markets, high volatility events
- **Best Times**: Mid-day trading (10 AM - 2 PM)

### Instrument Selection
- **Liquid Stocks**: High volume, tight spreads
- **ETFs**: Good for diversification
- **Avoid**: Low volume, wide spread instruments

### Monitoring and Adjustments
- Track performance metrics daily
- Adjust parameters based on market regime
- Review and update strategy monthly
- Keep detailed trade logs

## Common Pitfalls

1. **Overtrading**: Too many signals, too tight thresholds
2. **Ignoring Trends**: Fighting strong trends
3. **Poor Risk Management**: Not using stops, oversized positions
4. **Late-Day Entries**: Entering too close to market close
5. **Ignoring Volume**: Not considering volume context
6. **Parameter Overfitting**: Over-optimizing on historical data

## Performance Metrics to Track

- **Win Rate**: Percentage of profitable trades
- **Average Win/Loss**: Average profit vs. average loss
- **Profit Factor**: Gross profit / Gross loss
- **Sharpe Ratio**: Risk-adjusted returns
- **Maximum Drawdown**: Largest peak-to-trough decline
- **Daily/Weekly Returns**: Consistency of performance

## Example Trade Flow

### Long Trade Example
1. **10:30 AM**: Stock trading at $100, VWAP at $101.50 (1.5% below VWAP)
2. **Entry**: Buy at $100.00 (deviation threshold met)
3. **Stop Loss**: Set at $99.00 (1% risk)
4. **Target**: $101.50 (VWAP level)
5. **12:15 PM**: Price reaches $101.50, exit with 1.5% profit

### Short Trade Example
1. **11:00 AM**: Stock trading at $105, VWAP at $103.00 (1.9% above VWAP)
2. **Entry**: Sell short at $105.00 (deviation threshold met)
3. **Stop Loss**: Set at $106.00 (1% risk)
4. **Target**: $103.00 (VWAP level)
5. **1:30 PM**: Price reaches $103.00, exit with 1.9% profit

## Code Structure Recommendations

### Core Components
1. **Data Handler**: Fetch and process intraday data
2. **VWAP Calculator**: Calculate VWAP for each bar
3. **Signal Generator**: Identify entry/exit signals
4. **Risk Manager**: Position sizing and stop loss
5. **Order Manager**: Execute trades
6. **Performance Tracker**: Monitor and log results

### Key Functions
- `calculate_vwap()`: Compute VWAP
- `calculate_deviation()`: Measure price deviation from VWAP
- `generate_signals()`: Identify entry/exit points
- `calculate_position_size()`: Determine trade size
- `check_exit_conditions()`: Evaluate exit criteria
- `backtest_strategy()`: Test on historical data

## Conclusion

The Intraday VWAP Mean Reversion Strategy is a systematic approach that can be profitable when properly implemented with:
- Clear entry/exit rules
- Robust risk management
- Appropriate market selection
- Continuous monitoring and optimization

Remember: Past performance does not guarantee future results. Always backtest thoroughly and start with paper trading before risking real capital.

