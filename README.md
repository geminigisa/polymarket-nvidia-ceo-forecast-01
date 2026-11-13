# Polymarket "Next CEO of NVIDIA?" forecaster

Entry for make.fun bounty `polymarket-nvidia-ceo-forecast-01`: a program
that reads one case at a time — the minute-by-minute Yes prices of every
trading market of Polymarket's "Next CEO of NVIDIA?" event over the 72
hours up to a checkpoint — and forecasts each market's price at every
minute of the next 4 hours as five quantiles (5%, 25%, 50%, 75%, 95%).

## Method

Pure Python 3.13 standard library, offline, deterministic. No model is
called; everything the program knows is in the case it is given.

Prices in this event are sticky and jumpy: in about 30% of minutes the
price does not move at all, and when it moves the move is usually a few
tenths of a cent. A persistence forecast with a Normal spread wastes most
of its pinball loss on the inner quantiles, which it pushes away from the
last price even though the price usually stays put.

So the predictive distribution of the move at horizon `h` is a two-part
mixture, estimated from the market's own history at lags 1, 2, 4, 8, 16,
32, 64, 128 and 240 minutes:

- with probability `p0(h)` the price does not move at all (an atom at 0);
- otherwise the move is Normal(`drift(h)`, `s(h)`).

`p0(h)` is the fraction of zero moves at that lag; `s(h)` comes from the
median absolute deviation of the moves (robust to the occasional large
jump that would inflate a standard deviation), converted to a Normal
scale and shrunk by 0.60. Both are interpolated in log-horizon.
`drift(h)` is slow mean reversion of the median toward the market's
median price of the last 24 hours (time constant 1200 minutes).

Quantiles are the exact quantiles of that mixture — the atom makes the
25% and 75% quantiles sit exactly on the last price at short horizons —
clamped to [0, 1], rounded to 6 decimals, non-decreasing per row.

## Backtest

On the six practice cases (p00–p05; p05 truth from Polymarket's public
price history), mean pinball loss is about **0.293 percentage points**,
against **0.364** for the house persistence baseline — about 19% lower.
The backtest reproduces the kit's published baseline practice score
(0.363589) to within 1e-5, which validates the scoring code.

## Run

```sh
mkdir -p out
MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

Reads every `<id>.in` in the input directory and writes `<id>.out`
(`{"forecasts": [{"id", "q": [[...5 quantiles...] x 240]}]}`) to the
output directory. One case takes about 1–2 seconds, well under the
8-second cap, and two runs write byte-identical files.

## Files

- `main.py` — the forecaster (the whole entry).
- `LICENSE` — MIT.
