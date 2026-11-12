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

## Research process: what I tried, what worked and what didn't

Unless noted otherwise, all figures are for the development period (Oct 2016 – Sep 2021), after costs.

### Starting point: costs decide everything

Holding all six assets every day lost money (Sharpe −1.07, CAGR −19.1%), because the average open-to-close gain is smaller than the 0.10% round-trip cost. So any strategy has to trade **selectively**, only on days when the expected move is clearly larger than the cost. This shaped every idea below.

An early test of a simple lag-1 rule (follow or fade yesterday's direction, learned per asset) beat buy-and-hold in only 2–3 of 5 walk-forward splits. That's no better than chance, so trading every day on small daily patterns was ruled out.

### My own ideas

**1. Market-wide moves vs stock-specific moves.** *Worked, after refining.*

My hypothesis was that stocks don't move independently. A move shared by the whole market (for example, a reaction to economic news) should behave differently from a move caused by news about one company. I tested two versions:

| Version | What it measures | Result |
|---|---|---|
| **Market trend** (first attempt) | Has an equal-weight index of the six assets risen over the last 50 days? | Dev Sharpe 1.42, but **rejected**. Rebuilding the index without the asset being traded (leave-one-out) dropped the Sharpe to 1.23, with one split going negative. That suggested it mostly repeated each stock's own trend. It was also fragile: 7 of 12 nearby settings had a losing split. |
| **Market-driven** (refined) | Did the *other five* assets move more than 1% in the same direction *today*? | **Kept.** It tests the hypothesis directly. See the table below. |

What fading a big move (more than 3%) earned the next day, before costs:

| Type of big move | Count | Avg next-day return | Hit rate |
|---|---|---|---|
| Market-driven | 321 | **0.82%** | **59%** |
| Stock-specific (others within ±1%) | 305 | 0.20% | 52% |

**Market-driven moves reverse about four times more strongly.** A plausible explanation: market-wide moves are often crowd panic or forced selling that drags stocks down regardless of their value, while stock-specific moves are more often real information that sticks. As a strategy, fade + trend + market-driven scored a Sharpe of 1.42 with a max drawdown of −10.2%, compared with 0.43 for stock-specific moves only. In the final strategy, market-driven dips trigger buying. Across all 7 years, adding this to the dip-buying rule raised the 2022 Sharpe from 0.07 to 0.51.

**2. Regression lines for the trend.** *Worked, but not kept.*

My idea was to fit a regression line through recent log prices and use its slope as a smoother measure of trend direction.
- **On its own, as a momentum strategy** (long if the 60-day slope is up, short if down): Sharpe −1.21, the worst result tested. It trades every day and pays costs every day.
- **As a filter on mean reversion** (only fade moves in the direction of the slope): Sharpe 1.29, slightly better than the simple 100-day price change (1.26).

The simpler 100-day price change was kept for the final strategy. Both answer the same question (which way is the asset heading?), and the simple version is easier to explain and to calculate day by day. The small difference in development results was not enough to justify the extra complexity.


### Other strategy types tested

| Strategy | Type | Dev Sharpe | Verdict |
|---|---|---|---|
| Fade big moves (more than 3%) | Mean reversion | 0.90 | Worked. The core idea everything else builds on. |
| Fade with trend (only bet on reversals in the direction of the 100-day trend) | Mean reversion + momentum filter | 1.26 | Worked. Stable across 15 threshold and trend settings (Sharpe 0.75–1.31). |
| + volume confirmation (only fade moves on above-average volume) | Filter | 1.34 | **Worked.** It improved results at every setting from 0.8× to 1.3× normal volume, and cut max drawdown from −17.8% to −13.3%. Kept. |
| Fade up days only (short big spikes) | Mean reversion | 0.93 | Worked in development, but **failed in the holdout** (see below). |
| Bollinger bands (20-day, 2 standard deviations) | Mean reversion | 0.03 | Didn't work. |
| Pairs trade A–C (most correlated pair, 60-day spread z-score) | Statistical arbitrage | 0.14 | Didn't work. Too few profitable trades. |
| Momentum (regression slope) | Momentum | −1.21 | Didn't work on its own (see idea 2). |
| ETF arbitrage, market making | — | — | Not possible: there's no ETF data, and only one trade a day. |

### Risk and filter ideas that didn't work

| Idea | Result | Why |
|---|---|---|
| Smaller positions in volatile assets | Sharpe 1.26 → 1.24 | No real effect. |
| Skip or shrink trades when the market is turbulent | Sharpe 1.26 → 0.85–1.05 | **Hurt.** The strategy makes its money in turbulent markets, when overreactions happen. |
| Skip days when the whole market moved more than 2% | Sharpe 1.26 → 0.45 | **Hurt badly.** It removed the best (market-driven) trades. This was an early clue for idea 1. |
| Fade only stock-specific moves (relative to the market) | Sharpe 1.08 | Weaker, with two losing splits. Consistent with idea 1. |
| Adaptive switch (trade only if the strategy was profitable over the last 40–120 days) | Worse in 2017, 2019 and 2022 (all 7 years) | Too slow to react, and it switched off before recoveries. |
| Drawdown brake (halve exposure after a 5–15% drawdown) | Sharpe 1.00 → 1.06–1.10 (all 7 years) | Only a small improvement. Not kept. |
| Capping each asset at 25–50% of the portfolio | Max DD −14% → −4 to −7%, but CAGR 23% → 8–15% | A trade-off rather than an improvement. Not kept. |

### The holdout, and what it changed

The first frozen strategy was a ⅓ each blend of fade + trend + market-driven, fade + trend + volume, and fade up days only. It scored a Sharpe of 1.63 in development, but **−0.27** on the untouched holdout (Oct 2021 – Oct 2023):
- The core pattern weakened. Market-driven big moves reversed by only 0.03% the next day in the holdout, against 0.82% in development. 2022 was a steady bear market in which big moves often kept going instead of bouncing.
- **Short trades lost 16.5%, while long trades made 8.7%.**
- Only fade + trend + volume stayed positive (Sharpe 0.55).

Re-testing year by year on all 7 years showed that **dropping the shorts from dip buying** gave only one losing year out of seven, with a positive 2022. In an uptrend, buying panic dips held up; shorting rallies did not. The final strategy combines this long-only dip buying with fade + trend + volume. Keeping the volume strategy keeps the strategy trading often enough: long-only dip buying alone had only 36 active days in its quietest 3-year stretch, close to the 30-day minimum.

## Assumptions and limitations

- **Depends on volatile markets.** Much of the profit comes from turbulent periods, especially 2020. In calm markets the strategy trades rarely and earns little.
- **Sensitive to the trend window.** The 3% threshold is fairly robust, but results are noticeably worse with 50-day or 200-day trends instead of 100 days.
- **Trades rarely.** Average gross exposure is low, and the portfolio is in cash on most days. The quietest 3-year stretch in the development data still had 67 active days, above the competition minimum of 30.
- **Many variations were tested on the same 7 years,** so performance on the hidden period is likely to be lower than the results above.
- **The evaluator interface in the rules is provisional.** `strategy.py` may need small changes to match the organisers' final starter code.
