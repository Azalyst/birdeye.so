# Azalyst Alpha Scanner

An institutional-style on-chain signal platform for discovering and validating pump/dump, whale-accumulation, and smart-money patterns across 9 EVM and Solana chains. Runs entirely on GitHub Actions — no servers, no backend. Built on free public APIs. Not financial advice. Just systematic on-chain research.

<div align="center">

![Python](https://img.shields.io/badge/Python-3.11-blue?style=flat-square&logo=python)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)
![Status](https://img.shields.io/badge/Status-v2.0-brightgreen?style=flat-square)
![Runtime](https://img.shields.io/badge/Runtime-GitHub%20Actions-24292e?style=flat-square&logo=github)
![Chains](https://img.shields.io/badge/Chains-9-orange?style=flat-square)
![Model](https://img.shields.io/badge/Model-LightGBM%20%2B%20PrefixSpan-blueviolet?style=flat-square)
![Data](https://img.shields.io/badge/Data-DexScreener%20%2B%20GeckoTerminal%20%2B%20GoPlus-purple?style=flat-square)

### Live Operations
![Quant Cadence](https://img.shields.io/badge/Quant%20Scan-every%2015m-brightgreen?style=flat-square)
![ML Cadence](https://img.shields.io/badge/ML%20Refresh-2h%20%2F%20retrain%2024h-brightgreen?style=flat-square)
![Dashboard](https://img.shields.io/badge/Dashboard-GitHub%20Pages-success?style=flat-square)

</div>

**Live Dashboard:** [azalyst.github.io/Azalyst-Alpha-Scanner/dashboard.html](https://azalyst.github.io/Azalyst-Alpha-Scanner/dashboard.html)
**Maintained by:** [@gitdhirajsv](https://github.com/gitdhirajsv)

---

## What This Is

Azalyst Alpha Scanner is a **three-engine signal platform** that continuously scans Solana + EVM DEX activity for actionable patterns using 100% free, open public APIs:

1. **Quant Signal Engine** — rule-based + anomaly scoring over trending tokens, top traders, holder distribution, and trade aggregates. Commits a structured report every 15 minutes.
2. **NIM Qwen Agent** — a ReAct LLM agent (NVIDIA NIM / Qwen 2.5-Coder 32B) that autonomously invokes scanner tools and writes narrative reports on-demand or on schedule.
3. **Behavioral ML Pipeline** — wallet clustering + frequent-subsequence mining (PrefixSpan) + supervised LightGBM classifier that learns sequences like `whale_buy → anonymous_buy × N → pump` and scores each fresh signal with a calibrated probability.

All three write to the same SQLite database (`data/birdeye_quant.db`) and report directory (`reports/`) which is committed back to the repo after each run, so the **dashboard is a static page** that reads directly from the GitHub API.

---

## Data Sources (All Free, No Key Required*)

| Source | Provides | Key Required |
|---|---|---|
| **DexScreener** | Token overview, pair trades, price data | No |
| **GeckoTerminal** | Trending pools, new pools, OHLCV | No |
| **GoPlus Security** | Token security (mintable, freeze, holder concentration) | No |
| **Helius RPC** | Solana holder list, wallet transactions | Optional* |

*Helius enhances Solana data. The scanner runs without it; add `HELIUS_API_KEY` secret for richer Solana holder snapshots.

---

## Chains Supported

| Chain | Identifier | Chain | Identifier |
|---|---|---|---|
| Solana | `solana` | Avalanche | `avalanche` |
| Ethereum | `ethereum` | Polygon | `polygon` |
| Base | `base` | Optimism | `optimism` |
| Arbitrum | `arbitrum` | zkSync | `zksync` |
| BNB Chain | `bnb` | | |

---

## Architecture

```
              AZALYST ALPHA SCANNER — v2.0 SIGNAL STACK

  DATA SOURCES             INGESTION                 STORAGE
 DexScreener (free)    AzalystClient (retry 5xx)   SQLite (WAL)
 GeckoTerminal (free)  Token + pair + trade aggs   6 base tables
 GoPlus (free)         3-level retry, 1.5s jitter  5 ML tables
 Helius (optional)     Rate-limited serial writes  Committed in repo

  QUANT ENGINE            LLM AGENT                 ML PIPELINE
 Rule + anomaly score   NIM Qwen 2.5-Coder 32B      Wallet clustering
 Pump / dump / risk     ReAct loop (15 iter cap)    PrefixSpan mining
 Smart-money detection  Tool dispatch via JSON      LightGBM classifier
 9-chain universe       Reports to markdown         ml_prob per snapshot

  LABELING                SCHEDULER                DASHBOARD
 signal_outcomes table  GitHub Actions cron        dashboard.html (static)
 60-min horizon         Quant:  */15 min           Reads GH API directly
 10% target move        Agent:  */15 min           8 tabs incl. ML
 Evaluated per scan     ML:     */2h + daily       Live feed + pattern lib
                        Concurrency-grouped        Ops-rate excludes skips
```

---

## Operating Cadence

| Workflow | Schedule | Purpose |
|---|---|---|
| `quant_signal_engine.yml` | `*/15 * * * *` (every 15 min) | Rotating 3-chain scan with live trade/top-trader data; manual dispatch can run the full 9-chain universe |
| `agent.yml` | `*/15 * * * *` | NIM Qwen ReAct agent runs `daily_scan` + writes markdown reports |
| `ml_pipeline.yml` | `17 */2 * * *` + `13 3 * * *` | 2-hourly **refresh** (cluster→events→mine→score→export); daily **retrain** at 03:13 UTC |
| Dashboard | static | GitHub Pages — redeploys on every commit to `main` |

All write workflows share the `azalyst-signal-engine` concurrency group so DB/report writes are serialized end-to-end.

---

## Quick Start

### Run on GitHub Actions (recommended)

1. Fork this repository.
2. Add one required secret: `NIM_API_KEY` (free at [build.nvidia.com](https://build.nvidia.com) — for the LLM agent). Optionally add `HELIUS_API_KEY` (free at [helius.dev](https://helius.dev) — enhances Solana data).
3. Enable GitHub Actions on the fork. Workflows will begin firing within 15 minutes.
4. Open `https://<your-handle>.github.io/Azalyst-Alpha-Scanner/dashboard.html?repo=<your-handle>/Azalyst-Alpha-Scanner` — the dashboard reads your fork's data.

No cloud servers, no cron box, no database to manage. No paid API key required.

### Local Runs (development)

```bash
pip install -r requirements.txt

# Multi-chain scan → writes reports/latest_quant_signals.json + SQLite
python quant_signal_engine.py scan --chains "solana,base,ethereum,arbitrum,bnb" \
  --limit 20 --trade-limit 50 --evaluate \
  --outcome-horizon-min 60 --outcome-target-pct 10

# LLM agent — ReAct loop over Azalyst tools
python agent.py "run daily_scan and save results to reports/daily_scan.md"

# Behavioral ML pipeline
python -m ml all        # full: schema → cluster → events → mine → train → score → export
python -m ml refresh    # cheap: cluster → events → mine → score(recent) → export
python -m ml train      # standalone retrain
```

---

## Behavioral ML Pipeline

The ML layer learns **on-chain behavior sequences** directly from the quant engine's own stored history — no external labels, no separate data pipeline. It's deliberately **supervised, not reinforcement**: the problem is "given the 30-minute wallet-behavior window before a snapshot, predict whether the signal hits its target move," which is a classification task, not an agent-environment feedback loop.

### Wallet Clustering

Every wallet observed in `top_traders` is assigned to one of five clusters:

| Cluster | Rule |
|---|---|
| **whale** | Top 1% by cumulative volume + observed in ≥ 3 snapshots |
| **smart_money** | Top 5% by realized PnL + win-rate ≥ 55% + observed in ≥ 3 snapshots |
| **mm** | Buy/sell ratio in [0.85, 1.15] across ≥ 20 trades (market-maker flatness) |
| **sniper** | *(reserved — requires real on-chain creation timestamps; not active in v2)* |
| **anonymous** | Everything else (the default bucket) |

### Frequent-Subsequence Mining

For each snapshot, all `wallet_events` in the 30-minute lookback are serialized into a `(cluster, action)` token sequence, e.g.:

```
["whale_buy", "anonymous_buy", "anonymous_buy", "smart_money_buy", "anonymous_buy"]
```

PrefixSpan mines **frequent subsequences** (min support 5, length 2–4) across all tokens, then ranks them by **lift** against the `signal_outcomes.is_true` label. The top-40 patterns land in `pattern_library`; per-snapshot matches in `pattern_matches`.

These mined patterns are exported for research and the dashboard, but they are **not** used as live classifier features. That keeps the validation path free of pattern-label leakage.

Falls back to frequent-bigram counting if the `prefixspan` package isn't installed.

### Supervised Classifier

| Parameter | Value |
|---|---|
| **Primary model** | LightGBM (`n_estimators=300`, `lr=0.05`, `num_leaves=31`, `class_weight=balanced`) |
| **Fallback** | sklearn `GradientBoostingClassifier` |
| **Target** | `signal_outcomes.is_true` (binary, horizon = 60 min, target = 10% move) |
| **Features** | Token metrics · heuristic scores · trade-aggs ratios · 10 cluster-action counts |
| **Train/val split** | Chronological holdout (last 20%, minimum 10 rows) |
| **Min samples** | 50 labeled rows (refuses to train below — graceful cold-start) |
| **Artifacts** | `ml/model.pkl`, `ml/metrics.json` |

---

## Quant Signal Engine

### Scoring

The rule-based engine computes five scores per snapshot:

| Score | Range | Signals |
|---|---|---|
| `pump_score` | 0–100 | Whale accumulation · positive short-term price momentum · new listings |
| `dump_score` | 0–100 | Large holder liquidation · negative momentum · liquidity drain |
| `anomaly_score` | 0–100 | IsolationForest score over price/volume/holder features |
| `smart_money_score` | 0–100 | Top-trader concentration + positive PnL + recency |
| `risk_score` | 0–100 | Mintable authority · freeze authority · top-10 holder concentration · LP age |

Labels: `pump_candidate`, `whale_accumulation`, `dump_risk`, `anomaly_watch`, `avoid_high_risk`.

### Outcome Evaluation

`signal_outcomes` closes the loop — every scan also re-checks mature prior signals (age ≥ 60 min) and writes:

```
entry_price  current_price  return_pct  is_true  (↑ 10% within horizon? 1 : 0)
```

This `is_true` column is what the LightGBM classifier consumes as its training label. Ground truth is free and continuously accumulating.

---

## NIM Qwen Agent

A from-scratch ReAct loop (no LangChain, no framework) wired to 21 tools covering file I/O, shell, and 15 Azalyst scanner endpoints.

| Parameter | Value |
|---|---|
| **Model** | `qwen/qwen2.5-coder-32b-instruct` via NVIDIA NIM |
| **Loop** | Think → Tool → Observe → Repeat |
| **Iteration cap** | 15 |
| **Temperature** | 0.1 |
| **Tool format** | Triple-backtick `tool_call` blocks containing JSON `{tool, args}` |
| **Early exit** | `Final Answer:` sentinel in model output |

### Available Tools

`bash`, `read_file`, `write_file`, `list_dir`, `search`, `track_whale`, `find_pumps`, `analyze_token`, `daily_scan`, `get_profitable_traders`, `get_wallet_pnl`, `get_top_traders`, `check_token_security`, `get_new_listings`, `get_token_creation_info`, `get_holder_list`, `get_wallet_pnl_details`, `get_trader_txs`, `get_ohlcv`, `get_wallet_token_list`, `get_wallet_tx_list`.

---

## Data & Storage

### Database Schema

SQLite in WAL mode at `data/birdeye_quant.db`. Core tables:

| Table | Purpose |
|---|---|
| `tokens` | Distinct tokens seen, keyed on `(chain, address)` |
| `token_snapshots` | One row per token per scan — price, volume, holders, security flags |
| `trade_aggs` | Buy/sell counts + whale buy/sell volume per snapshot |
| `top_traders` | Per-wallet PnL/volume observed at each snapshot |
| `signals` | Scored snapshots — pump/dump/anomaly/smart-money/risk + label |
| `signal_outcomes` | Closed-loop evaluation — entry/current price, return_pct, is_true |

ML pipeline extends the schema:

| Table | Purpose |
|---|---|
| `wallet_clusters` | `(wallet, cluster, pnl_total_usd, volume_total_usd, snapshots_seen, win_rate)` |
| `wallet_events` | Synthesized `(snapshot_id, wallet, cluster, action, size_usd, size_bucket)` |
| `pattern_library` | Mined subsequences — `(prefix_json, length, support, lift, positive_rate)` |
| `pattern_matches` | Join of snapshots → matched patterns |
| `ml_scores` | `(snapshot_id, ml_prob, ml_direction, model_version)` |

### Reports Directory

| File | Writer | Consumer |
|---|---|---|
| `reports/latest_quant_signals.{json,csv}` | Quant engine | Dashboard — Intelligence tab |
| `reports/latest_quant_outcomes.{json,csv}` | Quant engine | Dashboard — Feed tab |
| `reports/latest_quant_brief.md` | Qwen brief mode | Human review |
| `reports/latest_ml_scores.json` | ML export | Dashboard — ML tab |
| `reports/quant_signals_<ts>.{json,csv}` | Quant engine (historical) | Archive |
| `reports/daily_scan.md` | NIM Qwen Agent | Human review |

---

## Dashboard

Static single-page app at `dashboard.html`, deployed via GitHub Pages. Uses the GitHub REST API directly — no backend, no build step, no auth required for public repos.

### Tabs

| Tab | Shows |
|---|---|
| **Intelligence** | Pump signals · dump warnings · whale moves · gems · chain pulse |
| **Traders** | Per-snapshot top-trader leaderboard by PnL |
| **Whales** | Observed wallet PnL summaries |
| **Gems** | New/low-cap tokens with pump signals and LP stats |
| **Security** | Rug risk (mintable, freeze authority, concentration) |
| **ML** | Model status · ROC AUC · cluster breakdown · top ML signals · pattern library by lift |
| **Chain Map** | Pump/dump heat per chain |
| **Live Feed** | Interleaved signal stream |
| **Reports** | Browse all committed reports |
| **System** | Workflow run health |

---

## Repository Structure

```
Azalyst-Alpha-Scanner/
│
├── quant_signal_engine.py        # Rule + anomaly scoring, outcome evaluation
├── agent.py                      # NIM Qwen ReAct loop
├── tools.py                      # 21-tool dispatcher for the agent
├── azalyst_tracker.py            # Multi-chain tracker (DexScreener + GeckoTerminal + GoPlus + Helius)
├── example_whale_tracking.py     # Standalone usage examples
│
├── agent/                        # Back-compat shims that load root
│   ├── agent.py
│   ├── tools.py
│   └── azalyst_tracker.py
│
├── ml/                           # Behavioral ML pipeline
│   ├── __main__.py               # CLI: schema|cluster|events|mine|train|score|export|all|refresh
│   ├── schema.py
│   ├── clustering.py
│   ├── events.py
│   ├── patterns.py
│   ├── features.py
│   ├── train.py
│   ├── score.py
│   ├── export.py
│   ├── model.pkl
│   └── metrics.json
│
├── .github/workflows/
│   ├── quant_signal_engine.yml   # Every 15 min — scan + evaluate
│   ├── agent.yml                 # Every 15 min — NIM Qwen ReAct run
│   ├── whale_tracking.yml        # On-demand whale scan
│   └── ml_pipeline.yml           # 2-hourly refresh + daily retrain
│
├── dashboard.html                # Static SPA — reads GH API, no backend
├── AGENTS.md                     # Agent system prompt
├── requirements.txt
├── README.md
│
├── data/
│   └── birdeye_quant.db          # SQLite (WAL) — committed, read by dashboard
└── reports/                      # JSON/CSV/MD exports (committed by workflows)
```

---

## Technical Specifications

| Parameter | Value |
|---|---|
| **Language** | Python 3.11 |
| **Runtime** | GitHub Actions (`ubuntu-latest`, 7GB RAM / 2 CPU / 14GB disk) |
| **Data sources** | DexScreener · GeckoTerminal · GoPlus · Helius (all free) |
| **HTTP client** | `requests` with 3-retry on 5xx + network errors, 1.5s jittered backoff |
| **Rate limiting** | Serial calls, 0.05s min delay between requests |
| **Storage** | SQLite with WAL, committed to repo as `data/birdeye_quant.db` |
| **LLM** | NVIDIA NIM Qwen 2.5-Coder 32B, temperature 0.1 |
| **ML primary** | LightGBM 4.1+ |
| **ML fallback** | sklearn GradientBoostingClassifier |
| **Sequence mining** | `prefixspan` 0.5+, bigram fallback |
| **Outcome horizon** | 60 min default (tunable via `--outcome-horizon-min`) |
| **Outcome target** | 10% price move (tunable via `--outcome-target-pct`) |
| **Retrain cadence** | Daily 03:13 UTC, minimum 50 labeled samples |
| **Concurrency** | All write-workflows share `azalyst-signal-engine` group |
| **Universe** | 9 chains, trending + new pools per chain |

---

## Operational Notes

### Secrets

| Secret | Purpose | Where to get | Required |
|---|---|---|---|
| `NIM_API_KEY` | NIM Qwen agent | [build.nvidia.com](https://build.nvidia.com) — free tier | Yes (agent only) |
| `HELIUS_API_KEY` | Solana RPC enhancements | [helius.dev](https://helius.dev) — free tier | No |

The quant scanner and ML pipeline run with **zero API keys**. Only the NIM Qwen agent requires a key.

### Concurrency

All write-workflows share `concurrency: azalyst-signal-engine` with `cancel-in-progress: false`. This serializes SQLite writes and git pushes — concurrent runs queue cleanly rather than racing.

### Runtime Budget

| Workflow | Typical duration | Hard timeout |
|---|---|---|
| Quant scan (2 chains, limit 20) | 90–200s | 15 min |
| Quant scan (multi-chain, limit 12) | 200–600s | 15 min |
| NIM Qwen agent (daily_scan) | 30–90s | 15 min |
| ML refresh | 30–90s | 30 min |
| ML full + retrain | 60–180s | 30 min |

Free GitHub Actions minutes on public repos are unlimited — the whole stack is zero operating cost.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| **0 signals in first scan** | Normal — GeckoTerminal/DexScreener may throttle on cold start. Second scan typically returns data. |
| **Agent runs SKIPPED on schedule** | Check `agent.yml` job-level `if:` includes `github.event_name == 'schedule'`. |
| **`NIM_API_KEY` secret missing** | Workflow fails with `::error::`. Set it in repo Settings → Secrets → Actions. |
| **ML tab empty on dashboard** | Pipeline not yet run — trigger manually via `gh workflow run ml_pipeline.yml`. |
| **Training fails "insufficient_data"** | Need ≥ 50 rows in `signal_outcomes` with `is_true IS NOT NULL`. Crosses threshold within 2–3 days. |
| **Git push conflicts** | Fixed — all workflows use `git pull --rebase -X theirs` before push. |
| **PrefixSpan not installed** | Falls back to frequent-bigram counting — pipeline still completes. |

---

## Version History

| Version | Date | Key Changes |
|---|---|---|
| **v0.x** | Q1 2026 | Initial multi-chain tracker — NIM Qwen agent + rule-based signals (Birdeye API) |
| **v1.0** | Apr 2026 | Behavioral ML pipeline, dashboard ML tab, schedule guard fix, concurrency-grouped workflows |
| **v2.0** | Apr 2026 | **Current** — Full rebuild on free APIs (DexScreener + GeckoTerminal + GoPlus + Helius); renamed to Azalyst Alpha Scanner; dropped paid Birdeye dependency |

---

## Roadmap

| Priority | Item | Status |
|---|---|---|
| ● | Real-time wallet tx ingestion via Helius webhooks (replace synthesized events) | not started |
| ● | True on-chain token creation timestamps → enable sniper cluster | not started |
| ○ | Regression head (expected `return_pct`) alongside the binary classifier | not started |
| ○ | Telegram/Discord alerting on high-confidence ML signals | not started |
| ○ | Historical price backfill for proper backtesting | not started |

---

## Related Projects

| Project | Visibility | Purpose |
|---|---|---|
| **Azalyst Alpha Scanner** (this repo) | Public | Real-time on-chain signal platform — free APIs |
| [Azalyst Alpha Research Engine](https://github.com/gitdhirajsv/Azalyst-Alpha-Research-Engine) | Public | OHLCV-based quantitative research — 77-week OOS walk-forward |
| **Azalyst Alpha Quant Research** | Private | Futures-grade quant research, the execution layer this project feeds |

---

## Disclaimer

This is a research and educational project. **Not financial advice.** On-chain signals, pump/dump detections, and ML probabilities are observations, not recommendations. Do your own research. Past on-chain behavior does not guarantee future price movement. Use at your own risk.

---

<div align="center">

**v2.0** | Built by [Azalyst](https://github.com/gitdhirajsv) | *Azalyst Alpha Quant Research*

*"Evidence over claims. Always."*

</div>
