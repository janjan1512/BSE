# BSE Quant Track: Trading Strategy Competition

A daily trading program for the BSE Quant Track competition. Each evening it reads the completed day's prices for Asset_A to Asset_G and returns the portfolio weights to trade at the next day's open. All positions close at that day's close.

## Files

| File | What it is |
|---|---|
| `strategy.py` | **The submission.** The `Strategy` class implements `on_day_close(daily_data, portfolio_state) -> weights`. |
| `backtester.py` | A local copy of the competition evaluator, used for development and testing. It is not part of the strategy. |
| `main.ipynb` | Research notebook: data checks, exploration, strategy development, walk-forward tests and holdout results. |
| `Fellows_Data/` | The provided development data, `Asset_A.csv` to `Asset_G.csv` (Oct 2016 – Oct 2023). |

## Requirements

- Python 3.11 or later (tested on 3.11 and 3.13)
- `numpy` and `pandas`, used by the strategy and the backtester
- `matplotlib` and `jupyter`, used only by the notebook

Tested with pandas 2.3.3, numpy 2.4.1 and matplotlib 3.10.0. Install with:

```bash
pip install numpy pandas matplotlib jupyter
```

The strategy uses no external data, no internet access and no randomness, so it gives the same weights every time it runs on the same data.

## How to run

### Use the strategy with the evaluator

```python
from strategy import Strategy

strategy = Strategy()

# The evaluator calls this once per completed trading day:
weights = strategy.on_day_close(daily_data, portfolio_state)
```

- **`daily_data`**: a dictionary keyed by asset (`"Asset_A"` to `"Asset_G"`). Each value is a dictionary with `Open`, `High`, `Low`, `Close` and `Volume` for the completed day.
- **`portfolio_state`**: provided by the evaluator. The current strategy does not use it.
- **Returns**: a dictionary with all 7 assets as signed fractions of equity. `sum(|w|) <= 1`, and `Asset_G` is always 0.

The strategy needs **101 days of history** before it can trade, because it uses a 100-day trend. It returns all-zero weights until then. The evaluator supplies the public development history before hidden scoring starts, so the strategy is fully warmed up by the first hidden day.

### Reproduce the development results locally

From this folder:

```bash
python3 -c "from backtester import *; from strategy import Strategy; log, m = run_simulation(Strategy(), load_data(), start='2016-10-28'); print_metrics(m, 'Final strategy')"
```

`run_simulation` feeds the strategy one day at a time in date order, the same way the evaluator does. It applies the competition rules: open-to-close returns, 0.05% entry and exit costs, and checks on the 100% gross-exposure limit.

### Notebook

Open `main.ipynb` in Jupyter or VS Code and run all cells from the top. After editing `strategy.py`, restart the kernel so the notebook loads the new version.

## Strategy summary

**Hypothesis:** large one-day moves driven by crowds, such as panic selling or market-wide shocks, tend to partly reverse the next day. Moves specific to one stock are more often real information and reverse less.

The final portfolio is a **50/50 blend of two sub-strategies**. Each one splits its half of the money equally across the assets it signals.

1. **Buy panic dips in uptrends** (long only). After an open-to-close drop of more than 3%, buy the asset the next day if:
   - it is above its price of 100 trading days ago (an uptrend), **and**
   - the drop came on above-average volume, **or** the other five assets also fell by more than 1% on average that day (a market-driven move).
2. **Fade + trend + volume** (long and short). After a move of more than 3% on above-average volume, bet on a reversal, but only in the direction of the 100-day trend: buy dips in uptrends and short spikes in downtrends.

Asset_G is excluded and always given a weight of 0, because it is an exact duplicate of Asset_B in the development data. The organisers confirmed it can be excluded.

All settings are fixed constants at the top of `generate_signals()` in `strategy.py`:

| Setting | Value | Meaning |
|---|---|---|
| `BIG_MOVE` | 0.03 | A big move is an open-to-close move larger than 3% |
| `TREND_DAYS` | 100 | Trend = today's close vs the close 100 trading days ago |
| `VOLUME_DAYS` | 20 | Normal volume = average of the previous 20 days |
| `VOLUME_MULT` | 1.0 | High volume = above that average |
| `OTHERS_MIN` | 0.01 | Market-driven = the other five assets moved more than 1% the same way |

## Development results

All results are after transaction costs, using the local backtester.

| Period | Sharpe | CAGR | Max drawdown | Active days |
|---|---|---|---|---|
| Full development data (Oct 2016 – Oct 2023) | 1.16 | 19.1% | −13.3% | 282 |
| Oct 2016 – Sep 2021 | 1.24 | 21.9% | −13.3% | 174 |
| Oct 2021 – Oct 2023 | 0.94 | 12.5% | −9.2% | 108 |

**How development was separated from validation:** strategies were first developed on Oct 2016 – Sep 2021 only, using walk-forward splits, and Oct 2021 – Oct 2023 was held back untouched. The first frozen strategy scored a Sharpe of **−0.27** on that holdout. Its short trades failed in the 2022 bear market. The final version above (long-only dip buying, blended with the volume strategy) was then chosen using all 7 years. **The Oct 2021 – Oct 2023 figures above are therefore not out-of-sample**, and no untouched data remains. The notebook records the original holdout result and the reason for the revision.

## Assumptions and limitations

- **Depends on volatile markets.** Much of the profit comes from turbulent periods, especially 2020. In calm markets the strategy trades rarely and earns little.
- **Sensitive to the trend window.** The 3% threshold is fairly robust, but results are noticeably worse with 50-day or 200-day trends instead of 100 days.
- **Trades rarely.** Average gross exposure is low, and the portfolio is in cash on most days. The quietest 3-year stretch in the development data still had 67 active days, above the competition minimum of 30.
- **Many variations were tested on the same 7 years,** so performance on the hidden period is likely to be lower than the results above.
- **The evaluator interface in the rules is provisional.** `strategy.py` may need small changes to match the organisers' final starter code.
