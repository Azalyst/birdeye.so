# Birdeye Quant Signal Engine

This is a direct Birdeye API scanner and ML-style signal engine for live token intelligence.
It records raw market snapshots into SQLite, aggregates trade behavior, and scores:

- sudden price and volume expansion
- whale accumulation or distribution
- smart-money pressure from top traders
- dump risk from sell imbalance and liquidity drops
- token security/rug-risk penalties
- anomaly watch using IsolationForest when `scikit-learn` is installed

It does not scrape Birdeye web pages. Use the official API with `BIRDEYE_API_KEY`.
For tradeable monitoring, use `--binance-usdt-only` to keep only tokens whose symbols match the live Binance USDT futures universe. The scanner also applies a minimum on-chain liquidity floor so same-symbol dust tokens do not flood the board.

## Install

```bash
cd birdeye.so-main
pip install -r requirements.txt
set BIRDEYE_API_KEY=your_key_here
```

PowerShell:

```powershell
$env:BIRDEYE_API_KEY="your_key_here"
```

## Run One Scan

```bash
python quant_signal_engine.py scan --chains all --limit 40 --binance-usdt-only
```

Outputs:

- SQLite database: `data/birdeye_quant.db`
- JSON report: `reports/quant_signals_YYYYMMDD_HHMMSS.json`
- CSV report: `reports/quant_signals_YYYYMMDD_HHMMSS.csv`

## Run Live

```bash
python quant_signal_engine.py loop --chains all --limit 40 --interval 300 --binance-usdt-only
```

This scans every 5 minutes and appends new snapshots into the same database.

## View Latest Stored Signals

```bash
python quant_signal_engine.py signals --show 50
```

## Evaluate True/False Outcomes

The scanner can verify whether old calls actually happened. For example, a pump call is marked true if price is at least `target_pct` higher after `horizon_min`; a dump call is true if price is at least `target_pct` lower.

```bash
python quant_signal_engine.py evaluate --horizon-min 60 --target-pct 10 --show 50
python quant_signal_engine.py outcomes --show 50
```

When scanning, use `--evaluate` to run this automatically:

```bash
python quant_signal_engine.py scan --chains all --limit 30 --binance-usdt-only --evaluate --outcome-horizon-min 60 --outcome-target-pct 10
```

Outcome reports:

- `reports/latest_quant_outcomes.json`
- `reports/latest_quant_outcomes.csv`
- `reports/quant_outcomes_YYYYMMDD_HHMMSS.json`

## GitHub Actions

The repository includes `.github/workflows/quant_signal_engine.yml`.

Required secret:

- `BIRDEYE_API_KEY`

Optional secret:

- `NIM_API_KEY` - writes a Qwen analyst brief to `reports/latest_quant_brief.md`

The scheduled job runs every 15 minutes, rotates through 3 chain batches when `--chains all` is selected, filters the universe down to Binance USDT futures symbols, and falls back to a committed futures cache if GitHub cannot reach Binance directly. It commits `latest_quant_signals.json`, evaluates older signals, and updates the dashboard data.

## Useful Modes

Fast Binance futures watch:

```bash
python quant_signal_engine.py loop --chains all --limit 25 --trade-limit 50 --interval 120 --binance-usdt-only
```

Multi-chain watch:

```bash
python quant_signal_engine.py loop --chains all --limit 50 --interval 600 --binance-usdt-only
```

Cheaper API mode:

```bash
python quant_signal_engine.py scan --chains all --limit 20 --trade-limit 30 --top-trader-limit 0 --no-new-listings --binance-usdt-only
```

## Signal Labels

`pump_candidate`
: Strong price/volume expansion, buy pressure, whale or smart-money confirmation, and tolerable risk.

`whale_accumulation`
: Net large-wallet buying with positive trade imbalance.

`anomaly_watch`
: Token looks statistically unusual versus the current scan batch or heuristic baseline.

`dump_risk`
: Sell pressure, whale distribution, price decline, or liquidity contraction.

`avoid_high_risk`
: Security or holder-concentration risk is too high for the signal quality.

`watch`
: Interesting enough to keep recording, not strong enough for an alert.

## How Scores Work

Pump score:

- positive 1h price change
- 1h volume versus 24h hourly baseline
- buy/sell volume imbalance
- large-wallet net flow
- holder growth
- positive top-trader participation
- minus security risk

Dump score:

- negative 1h price change
- sell volume imbalance
- whale sell net flow
- liquidity drop
- holder outflow
- plus security risk

Smart-money score:

- top trader PnL
- top trader volume
- number of profitable top traders
- current buy pressure
- minus security risk

Anomaly score:

- IsolationForest on the current scan batch when `scikit-learn` is available
- otherwise a robust heuristic using price jump, volume expansion, imbalance, whale flow, and liquidity change

## Database Tables

- `tokens`: token identity and first/last seen timestamps
- `token_snapshots`: token overview and security snapshots
- `trade_aggs`: buy/sell/whale flow aggregates per snapshot
- `top_traders`: top-trader rows per snapshot
- `signals`: pump/dump/anomaly/smart-money/risk scores and reasons

## Important Notes

- This is a decision-support system, not an auto-trader.
- Run it for a few days before trusting thresholds.
- Low-cap token data can be noisy or manipulated.
- A high pump score with high risk should be treated as a danger signal, not an entry.
- For production, run with an API key and choose intervals that respect your Birdeye plan.
