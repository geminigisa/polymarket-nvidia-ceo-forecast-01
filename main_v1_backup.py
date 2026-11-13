#!/usr/bin/env python3
"""Minute-by-minute Polymarket "Next CEO of NVIDIA?" forecaster.

Method (pure Python 3.13 standard library, offline, deterministic):

For each market, the 1-minute Yes prices of the last 72 hours are treated as
a sticky, jumpy series: most minutes the price does not move at all, and
when it moves the move is small.  A plain persistence + Normal-spread
forecast wastes most of its pinball loss on the inner quantiles, which it
pushes away from the last price even though the price usually stays put.

So the predictive distribution of the move at horizon h is a two-part
mixture, estimated from the market's own history at several lags:

  * with probability p0(h) the price does not move at all (an atom at 0);
  * otherwise the move is Normal(drift(h), s(h)).

p0(h) and the move scale s(h) are measured empirically at lags
1, 2, 4, 8, 16, 32, 64, 128 and 240 minutes (fraction of zero moves, and
the median absolute deviation of the moves, which is robust to the
occasional large jump that would inflate a standard deviation), then
interpolated in log-horizon.  s(h) is the MAD converted to a Normal scale
(1.4826 * MAD / sqrt(1 - p0)) and shrunk by S_SCALE = 0.60, the centre of
the flat optimum found in backtests.

drift(h) is slow mean reversion of the median toward the market's median
price of the last 24 hours, with time constant 1200 minutes:
drift(h) = (mu - x) * (1 - exp(-h / 1200)).

Quantiles are the exact quantiles of that mixture (the atom makes the
25% and 75% quantiles sit exactly on the last price at short horizons,
which is where the pinball gain comes from), clamped to [0, 1], rounded
to 6 decimals, and sorted so every row is non-decreasing.

Backtest on the six practice cases (p00-p05; p05 truth from Polymarket's
public price history): mean pinball loss about 0.293 percentage points,
against 0.364 for the house persistence baseline (sigma 0.0025) — about
19% lower.  The backtest reproduces the kit's published baseline practice
score (0.363589) to within 1e-5, which validates the scoring code.

Reads every <id>.in in the input directory and writes <id>.out to the
output directory.  Outside the grader, MAKEFUN_INPUT_DIR and
MAKEFUN_OUTPUT_DIR stand in for /input and /output.
"""

import json
import math
import os
import statistics
from statistics import NormalDist

INPUT_DIR = os.environ.get("MAKEFUN_INPUT_DIR", "/input")
OUTPUT_DIR = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")

# The quantile levels the contest scores, in the order each row lists them.
QUANTILES = [0.05, 0.25, 0.5, 0.75, 0.95]
# Lags (minutes) at which the move distribution is measured from history.
LAGS = [1, 2, 4, 8, 16, 32, 64, 128, 240]
# Shrinkage of the MAD-based move scale (centre of the flat backtest optimum).
S_SCALE = 0.60
# Mean-reversion time constant (minutes) toward the 24-hour median price.
MEAN_REV_TAU = 1200.0
# Window (minutes) for the mean-reversion level.
MU_WINDOW = 1440

_ND = NormalDist()


def _clamp01(x):
    return min(1.0, max(0.0, x))


def _price6(x):
    """x clamped to [0, 1] and rounded to 6 decimals (0, never -0)."""
    return round(_clamp01(x), 6) + 0.0


def _interp(xs, ys, x):
    """Linear interpolation in log-x; flat extrapolation outside the range."""
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    lx = math.log(x)
    for i in range(len(xs) - 1):
        if xs[i] <= x <= xs[i + 1]:
            a, b = math.log(xs[i]), math.log(xs[i + 1])
            t = (lx - a) / (b - a) if b > a else 0.0
            return ys[i] * (1.0 - t) + ys[i + 1] * t
    return ys[-1]


def _lag_stats(prices):
    """Per lag: (fraction of zero moves, MAD of the moves).

    Returns (lags, p0s, mads) with only the lags that have enough history.
    """
    n = len(prices)
    lags, p0s, mads = [], [], []
    for lag in LAGS:
        if n <= lag + 10:
            continue
        moves = [prices[i + lag] - prices[i] for i in range(n - lag)]
        m = len(moves)
        p0 = sum(1 for d in moves if d == 0) / m
        med = statistics.median(moves)
        mad = statistics.median([abs(d - med) for d in moves])
        lags.append(lag)
        p0s.append(p0)
        mads.append(mad)
    return lags, p0s, mads


def _forecast(prices, horizon, quantiles):
    """240 (horizon) rows of quantiles for one market's price series."""
    if not prices:
        return [[0.5 for _ in quantiles] for _ in range(horizon)]
    x = prices[-1]
    lags, p0s, mads = _lag_stats(prices)
    if not lags:
        # Too little history for the mixture: narrow fixed spread fallback.
        return [
            [_price6(x + z * 0.00125 * math.sqrt(h)) for z in (-1.644854, -0.67449, 0.0, 0.67449, 1.644854)]
            for h in range(1, horizon + 1)
        ]
    # Mean-reversion level: median price of the last 24 hours.
    window = prices[-MU_WINDOW:] if len(prices) > MU_WINDOW else prices[:]
    mu = statistics.median(window)
    rows = []
    for h in range(1, horizon + 1):
        p0 = min(0.9, max(0.02, _interp(lags, p0s, h)))
        mad = max(0.0001, _interp(lags, mads, h))
        s = 1.4826 * mad / math.sqrt(max(0.05, 1.0 - p0)) * S_SCALE
        drift = (mu - x) * (1.0 - math.exp(-h / MEAN_REV_TAU))
        # The mixture CDF jumps by p0 at a move of 0: its value just below 0
        # is (1 - p0) / 2 and just above 0 is (1 - p0) / 2 + p0.
        lo = (1.0 - p0) * 0.5
        hi = lo + p0
        row = []
        for tau in quantiles:
            if tau < lo:
                q = drift + s * _ND.inv_cdf(tau / (1.0 - p0))
            elif tau > hi:
                q = drift + s * _ND.inv_cdf((tau - p0) / (1.0 - p0))
            else:
                q = 0.0
            row.append(_price6(x + q))
        rows.append([round(v, 6) + 0.0 for v in sorted(row)])
    return rows


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    inputs = sorted(f for f in os.listdir(INPUT_DIR) if f.endswith(".in"))
    for name in inputs:
        case_id = name[: -len(".in")]
        with open(os.path.join(INPUT_DIR, name), "r", encoding="utf-8") as f:
            case = json.load(f)
        horizon = int(case["horizon_minutes"])
        quantiles = list(case.get("quantiles", QUANTILES))
        forecasts = [
            {"id": m["id"], "q": _forecast(m["prices"], horizon, quantiles)}
            for m in case["markets"]
        ]
        out_path = os.path.join(OUTPUT_DIR, case_id + ".out")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(json.dumps({"forecasts": forecasts}) + "\n")


if __name__ == "__main__":
    main()
