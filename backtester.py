"""
Local copy of the BSE Quant Track competition evaluator.

It follows the rules in BSE_Quant_Track_Trading_Competition_Rules_Original_Style.pdf:
  - Positions open at the day's Open and close at the same day's Close (no overnight).
  - Weights are signed fractions of equity; sum of |weights| must be <= 1.
  - Costs: 0.05% of entry notional + 0.05% of exit notional, on every position.
  - The strategy only sees completed days. It decides tomorrow's weights at today's close.
  - Scoring: Sharpe (50 pts), CAGR (30 pts), Max drawdown (20 pts).

The official interface is provisional, so check this against the organiser's
starter code when it is released.
"""

from pathlib import Path

import numpy as np
import pandas as pd

ASSETS = [f"Asset_{x}" for x in "ABCDEFG"]       # keys the output must contain
TRADABLE = [f"Asset_{x}" for x in "ABCDEF"]      # G excluded (organisers confirmed; duplicate of B)
COST_RATE = 0.0005          # 5 bp on entry and 5 bp on exit
TRADING_DAYS = 252
DATA_DIR = Path(__file__).parent / "Fellows_Data"


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #
def load_data(data_dir=DATA_DIR):
    """Load all 7 CSVs into one long table: Date, Asset, Open, High, Low, Close, Volume."""
    frames = []
    for asset in ASSETS:
        df = pd.read_csv(Path(data_dir) / f"{asset}.csv", parse_dates=["Date"])
        df = df.rename(columns={"Close/Last": "Close"})
        for col in ["Open", "High", "Low", "Close"]:
            df[col] = df[col].astype(str).str.replace("$", "", regex=False).astype(float)
        df["Asset"] = asset
        frames.append(df)
    data = pd.concat(frames).sort_values(["Date", "Asset"]).reset_index(drop=True)
    return data[["Date", "Asset", "Open", "High", "Low", "Close", "Volume"]]


def wide(data, field):
    """One column per asset for a single field, e.g. wide(data, 'Close')."""
    return data.pivot(index="Date", columns="Asset", values=field)[ASSETS]


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
def validate_weights(weights):
    """Raise an error if weights break the competition rules."""
    if set(weights) != set(ASSETS):
        raise ValueError(f"Weights must have exactly these keys: {ASSETS}")
    values = np.array([weights[a] for a in ASSETS], dtype=float)
    if not np.all(np.isfinite(values)):
        raise ValueError(f"Weights must be finite numbers: {weights}")
    for a in ASSETS:
        if a not in TRADABLE and weights[a] != 0:
            raise ValueError(f"{a} is excluded and must have weight 0, got {weights[a]}")
    if np.abs(values).sum() > 1 + 1e-9:
        raise ValueError(f"Gross exposure {np.abs(values).sum():.4f} is over 1.0")


def daily_portfolio_returns(weights, open_px, close_px):
    """
    Net daily portfolio return after costs.

    weights:  DataFrame (Date x Asset), the weights traded ON that date.
    open_px / close_px: DataFrames of the same shape.
    """
    oc_return = close_px / open_px - 1
    w = weights.reindex_like(oc_return).fillna(0.0)
    gross = (w * oc_return).sum(axis=1)
    entry_cost = COST_RATE * w.abs().sum(axis=1)
    exit_cost = COST_RATE * (w.abs() * (1 + oc_return)).sum(axis=1)
    return gross - entry_cost - exit_cost


def metrics(returns, weights=None):
    """Sharpe, CAGR, max drawdown and a few extras, from daily net returns."""
    returns = returns.dropna()
    equity = (1 + returns).cumprod()
    std = returns.std()
    out = {
        "sharpe": returns.mean() / std * np.sqrt(TRADING_DAYS) if std > 0 else 0.0,
        "cagr": equity.iloc[-1] ** (TRADING_DAYS / len(returns)) - 1,
        "max_drawdown": (equity / equity.cummax() - 1).min(),
        "total_return": equity.iloc[-1] - 1,
        "daily_vol": std,
        "min_equity": equity.min(),
    }
    if weights is not None:
        out["active_days"] = int((weights.abs().sum(axis=1) > 0).sum())
        out["avg_gross_exposure"] = weights.abs().sum(axis=1).mean()
    return out


def evaluate_weights(weights, data, start=None, end=None):
    """
    Fast research backtest: score a whole DataFrame of weights at once.

    IMPORTANT: weights on row t must only use data up to day t-1.
    The usual way is to compute a signal from day t's data, then .shift(1).
    """
    open_px, close_px = wide(data, "Open"), wide(data, "Close")
    w = weights.reindex(columns=ASSETS).fillna(0.0)
    excluded = [a for a in ASSETS if a not in TRADABLE]
    if (w[excluded] != 0).any().any():
        raise ValueError(f"{excluded} are excluded and must have weight 0")
    if start is not None:
        w = w.loc[start:]
    if end is not None:
        w = w.loc[:end]
    gross = w.abs().sum(axis=1)
    if (gross > 1 + 1e-9).any():
        raise ValueError(f"Gross exposure over 1.0 on {int((gross > 1 + 1e-9).sum())} days")
    rets = daily_portfolio_returns(w, open_px.loc[w.index], close_px.loc[w.index])
    return rets, metrics(rets, w)


# --------------------------------------------------------------------------- #
# Day-by-day simulation (the way the real evaluator runs your program)
# --------------------------------------------------------------------------- #
def run_simulation(strategy, data, start, end=None):
    """
    Feed the strategy one completed day at a time, exactly like the evaluator.

    Days before `start` are warm-up history (the strategy sees them but nothing is traded).
    Trading is scored from `start` to `end`.
    """
    dates = sorted(data["Date"].unique())
    by_date = {d: g.set_index("Asset") for d, g in data.groupby("Date")}
    start, end = pd.Timestamp(start), pd.Timestamp(end) if end else dates[-1]

    equity, peak = 1.0, 1.0
    prev_weights = {a: 0.0 for a in ASSETS}
    next_weights = None
    records = []

    for date in dates:
        today = by_date[date]

        # 1. Execute yesterday's decision at today's open, close at today's close
        if next_weights is not None and start <= date <= end:
            ret = 0.0
            for a in ASSETS:
                w = next_weights[a]
                oc = today.loc[a, "Close"] / today.loc[a, "Open"] - 1
                ret += w * oc - COST_RATE * abs(w) * (2 + oc)
            equity *= 1 + ret
            peak = max(peak, equity)
            records.append({"Date": date, "return": ret, "equity": equity, **next_weights})
            prev_weights = next_weights
            if equity <= 0:
                raise RuntimeError(f"Equity hit zero on {date.date()}, disqualified")

        if date > end:
            break

        # 2. Give the strategy today's completed bar; it returns tomorrow's weights
        daily_data = {
            a: today.loc[a, ["Open", "High", "Low", "Close", "Volume"]].to_dict() | {"Date": date}
            for a in ASSETS
        }
        portfolio_state = {"equity": equity, "peak_equity": peak, "previous_weights": dict(prev_weights)}
        next_weights = strategy.on_day_close(daily_data, portfolio_state)
        validate_weights(next_weights)

    log = pd.DataFrame(records).set_index("Date")
    weights = log[ASSETS]
    return log, metrics(log["return"], weights)


def print_metrics(m, label=""):
    if label:
        print(label)
    print(f"  Sharpe        {m['sharpe']:.2f}")
    print(f"  CAGR          {m['cagr']:.1%}")
    print(f"  Max drawdown  {m['max_drawdown']:.1%}")
    print(f"  Total return  {m['total_return']:.1%}")
    if "active_days" in m:
        print(f"  Active days   {m['active_days']}  (need >= 30)")
        print(f"  Avg exposure  {m['avg_gross_exposure']:.2f}")
