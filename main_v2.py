#!/usr/bin/env python3
"""Minute-by-minute Polymarket "Next CEO of NVIDIA?" forecaster — V2-Final (B1+D1).

Candidate challenger to V1 (repo-v2/main.py, practice 0.292874).
Practice score of THIS file: mean pinball 0.286869
(p00 0.4546, p01 0.3148, p02 0.3652, p03 0.3404, p04 0.1934, p05 0.1122)
— wins all 6 practice cases vs V1 and vs B1-alone (0.288800).
Second change vs B1: D1 regime scale from history only —
stagnan (p0 lag-1 > 0.9) s x0.8; normal x1.0; jump (move >0.05 in last
60 min OR p0 lag-1 < 0.5) s x1.3. Student-t was tested on top and
REJECTED: B1+t5 alone 0.289285 (worse than B1), B1+D1+t5 0.287250
(worse than B1+D1); only B1+D1+t5 at re-tuned s=0.55 reached 0.286511,
a marginal +0.00036 that loses 2/6 cases vs B1+D1 and needs a scale
retune contradicting the no-t optimum — judged noise, not kept.

What changed vs V1 (exactly one estimator change + one re-tuned constant):
  * V1 measured the move scale as MAD of ALL lag moves (zeros included):
    s = 1.4826 * MAD_all / sqrt(1 - p0) * 0.60.  In practice 57.1% of
    (market, lag) pairs have MAD_all == 0 (more than half the moves are
    zero), so s collapsed to the 0.0001 floor and the forecast went
    nearly degenerate — while |drift|/s exploded (p99 up to 16.7 at h=15).
  * This file measures MAD of the NONZERO moves only and drops the
    sqrt(1 - p0) correction (that correction exists only to undo the
    zero-moves' drag on MAD_all; with MAD_nonzero it would double-count):
    s = 1.4826 * MAD_nonzero * 0.50.
    Only 0.3% of (market, lag) pairs still hit the floor.
  * S_SCALE re-tuned 0.60 -> 0.50 for the new estimator (practice curve
    0.40: 0.292414, 0.45: 0.290113, 0.50: 0.288800, 0.55: 0.289029,
    0.60: 0.289947, 0.70: 0.293298 — interior optimum, flat 0.45-0.60).

What was DELIBERATELY kept from V1 (audit finding):
  * The atom bounds lo = (1 - p0) / 2, hi = lo + p0.  The mathematically
    exact bounds lo = (1 - p0) * Phi(-drift / s) were tested as V2-A and
    LOST on practice at every scale (0.294628 at s=0.60, 0.290543 at
    s=0.50 for the B1 combination): V1's symmetric bounds pin the median
    to the last price in 86.7% of rows, and the drift centre is too
    misspecified for the median — the "correct" bounds move the median
    off the last price in 35.5% of rows and cost +0.0075 on the t50
    pinball alone.  Do NOT "fix" the atom bounds without fresh evidence.

Everything else is byte-identical logic to V1: same LAGS, same log-horizon
interpolation, same mean-reversion drift (tau 1200 min toward the 24h
median), same p0 clamp [0.02, 0.9], same fallback, same clamp/round/sort.

Pure Python 3.13 standard library, offline, deterministic.
Reads every <id>.in in the input directory, writes <id>.out to output.
"""
import json
import math
import os
import statistics
from statistics import NormalDist

INPUT_DIR = os.environ.get("MAKEFUN_INPUT_DIR", "/input")
OUTPUT_DIR = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")

QUANTILES = [0.05, 0.25, 0.5, 0.75, 0.95]
LAGS = [1, 2, 4, 8, 16, 32, 64, 128, 240]
# MAD-nonzero scale shrinkage (re-tuned for this estimator; V1 used 0.60
# with MAD-of-all-moves).
S_SCALE = 0.50
MEAN_REV_TAU = 1200.0
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
    """Per lag: (fraction of zero moves, MAD of the NONZERO moves).

    Returns (lags, p0s, mads_nz) with only the lags that have enough history.
    mad_nz is 0.0 when a lag has no nonzero move at all (then the scale
    floor below applies, as in V1).
    """
    n = len(prices)
    lags, p0s, mads = [], [], []
    for lag in LAGS:
        if n <= lag + 10:
            continue
        moves = [prices[i + lag] - prices[i] for i in range(n - lag)]
        m = len(moves)
        p0 = sum(1 for d in moves if d == 0) / m
        nz = [d for d in moves if d != 0]
        if nz:
            med_nz = statistics.median(nz)
            mad_nz = statistics.median([abs(d - med_nz) for d in nz])
        else:
            mad_nz = 0.0
        lags.append(lag)
        p0s.append(p0)
        mads.append(mad_nz)
    return lags, p0s, mads


def _regime_scale(prices):
    """0.8 stagnan / 1.0 normal / 1.3 jump, from history only."""
    if len(prices) < 70:
        return 1.0
    d1 = [prices[i + 1] - prices[i] for i in range(len(prices) - 1)]
    p0_1 = sum(1 for d in d1 if d == 0) / len(d1)
    mj = max((abs(d) for d in d1[-60:]), default=0.0)
    if mj > 0.05 or p0_1 < 0.5:
        return 1.3
    if p0_1 > 0.9:
        return 0.8
    return 1.0


def _forecast(prices, horizon, quantiles=QUANTILES):
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
    s_mult = _regime_scale(prices)
    rows = []
    for h in range(1, horizon + 1):
        p0 = min(0.9, max(0.02, _interp(lags, p0s, h)))
        mad = max(0.0001, _interp(lags, mads, h))
        # NOTE: no /sqrt(1-p0) — the nonzero-MAD already estimates the
        # conditional (nonzero-move) scale directly.
        s = 1.4826 * mad * S_SCALE * s_mult
        drift = (mu - x) * (1.0 - math.exp(-h / MEAN_REV_TAU))
        # Atom bounds kept symmetric as in V1 (see module docstring:
        # the drift-corrected bounds lose on practice).
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
