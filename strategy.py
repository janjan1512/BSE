"""
Submission template for the BSE Quant Track competition.

The evaluator calls on_day_close() once per completed trading day and trades the
returned weights at the NEXT day's open, closing them at that day's close.

Rules to keep in mind:
  - Return all 7 assets, Asset_A to Asset_G, as signed fractions of equity.
  - sum(|weights|) must be <= 1.
  - Only use data you have already been given (self.history). Never look ahead.
  - Every position costs about 0.10% round trip, so only trade when the edge beats that.
"""

import numpy as np
import pandas as pd

ASSETS = [f"Asset_{x}" for x in "ABCDEFG"]       # keys the output must contain
TRADABLE = [f"Asset_{x}" for x in "ABCDEF"]      # G excluded: always weight 0


class Strategy:
    def __init__(self, max_gross=1.0):
        self.max_gross = max_gross
        self.history = {a: [] for a in ASSETS}   # list of daily bars per asset

    # ------------------------------------------------------------------ #
    # Required interface
    # ------------------------------------------------------------------ #
    def on_day_close(self, daily_data, portfolio_state):
        # 1. Store the newly completed day
        for a in ASSETS:
            self.history[a].append(daily_data[a])

        # 2. Build signals from history only
        raw = self.generate_signals()

        # 3. Turn signals into weights that respect the gross-exposure limit
        weights = self.size_positions(raw, portfolio_state)
        return weights

    # ------------------------------------------------------------------ #
    # Your logic goes here
    # ------------------------------------------------------------------ #
    # Strategy settings (fixed before evaluation; chosen on the development data)
    BIG_MOVE = 0.03        # a "big move" is an open-to-close move larger than 3%
    TREND_DAYS = 100       # trend = price today vs 100 trading days ago
    VOLUME_DAYS = 20       # "normal" volume = average of the previous 20 days
    VOLUME_MULT = 1.0      # high volume = above that average
    OTHERS_MIN = 0.01      # market-driven = other five assets moved >1% the same way

    def generate_signals(self):
        """
        FINAL v2: 50/50 blend of two sub-strategies, each splitting its money
        equally across the assets it signals.

        Sub-strategy 1, "Buy panic dips in uptrends" (long only):
            buy an asset after a >3% drop, if it is in a 100-day uptrend AND
            the drop came on high volume OR was market-wide.

        Sub-strategy 2, "Fade + trend + volume" (long and short):
            after a >3% move on above-average volume, bet on a reversal,
            but only in the direction of the 100-day trend.
        """
        signals = {a: 0.0 for a in ASSETS}

        # Need TREND_DAYS + 1 closes for the trend and VOLUME_DAYS + 1 volumes for the volume ratio
        n_needed = max(self.TREND_DAYS, self.VOLUME_DAYS) + 1
        if len(self.history[TRADABLE[0]]) < n_needed:
            return signals

        # --- Today's measurements for each asset (only completed data) ---
        move, trend, high_volume = {}, {}, {}
        for a in TRADABLE:
            bars = self.history[a]
            today = bars[-1]
            move[a] = today["Close"] / today["Open"] - 1
            trend[a] = np.sign(today["Close"] / bars[-1 - self.TREND_DAYS]["Close"] - 1)
            normal_volume = np.mean([b["Volume"] for b in bars[-1 - self.VOLUME_DAYS:-1]])
            high_volume[a] = today["Volume"] / normal_volume > self.VOLUME_MULT

        # --- Build each sub-strategy's signals (+1 long, -1 short, 0 flat) ---
        dips, fade_volume = {}, {}
        for a in TRADABLE:
            big = abs(move[a]) > self.BIG_MOVE
            fade = -np.sign(move[a]) if big else 0.0          # bet on a reversal
            agrees_with_trend = fade != 0 and np.sign(fade) == trend[a]

            others = np.mean([move[b] for b in TRADABLE if b != a])
            market_driven = big and np.sign(others) == np.sign(move[a]) and abs(others) > self.OTHERS_MIN

            # Sub-strategy 1: long only
            dips[a] = 1.0 if (fade > 0 and trend[a] > 0 and (high_volume[a] or market_driven)) else 0.0
            # Sub-strategy 2: long or short
            fade_volume[a] = fade if (agrees_with_trend and high_volume[a]) else 0.0

        # --- Split each sub-strategy's money equally, then blend 50/50 ---
        for sub in (dips, fade_volume):
            n = sum(abs(s) for s in sub.values())
            if n > 0:
                for a in TRADABLE:
                    signals[a] += 0.5 * sub[a] / n

        return signals

    def size_positions(self, signals, portfolio_state):
        """Scale signals so that sum(|w|) <= max_gross."""
        signals = {a: (signals.get(a, 0.0) if a in TRADABLE else 0.0) for a in ASSETS}
        gross = sum(abs(s) for s in signals.values())
        if gross == 0:
            return {a: 0.0 for a in ASSETS}
        scale = min(1.0, self.max_gross / gross)
        return {a: float(signals[a] * scale) if a in TRADABLE else 0.0 for a in ASSETS}

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def bars(self, asset):
        """All completed bars for one asset as a DataFrame."""
        return pd.DataFrame(self.history[asset])

    def closes(self, asset):
        return pd.Series([bar["Close"] for bar in self.history[asset]], dtype=float)
