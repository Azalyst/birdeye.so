# Azalyst Birdeye Scanner

An institutional-style on-chain signal platform for discovering and validating pump/dump, whale-accumulation, and smart-money patterns across 9 EVM and Solana chains. Runs entirely on GitHub Actions — no servers, no backend. Built as a personal project. Not a hedge fund. Not a financial product. Just systematic on-chain research.

<div align="center">

![Python](https://img.shields.io/badge/Python-3.11-blue?style=flat-square&logo=python)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)
![Status](https://img.shields.io/badge/Status-v1.0-brightgreen?style=flat-square)
![Runtime](https://img.shields.io/badge/Runtime-GitHub%20Actions-24292e?style=flat-square&logo=github)
![Chains](https://img.shields.io/badge/Chains-9-orange?style=flat-square)
![Model](https://img.shields.io/badge/Model-LightGBM%20%2B%20PrefixSpan-blueviolet?style=flat-square)
![Data](https://img.shields.io/badge/Data-Birdeye%20API-purple?style=flat-square)

### Live Operations
![Quant Cadence](https://img.shields.io/badge/Quant%20Scan-every%2015m-brightgreen?style=flat-square)
![ML Cadence](https://img.shields.io/badge/ML%20Refresh-2h%20%2F%20retrain%2024h-brightgreen?style=flat-square)
![Dashboard](https://img.shields.io/badge/Dashboard-GitHub%20Pages-success?style=flat-square)

</div>

**Live Dashboard:** [azalyst.github.io/Azalyst-Birdeye-Scanner/dashboard.html](https://azalyst.github.io/Azalyst-Birdeye-Scanner/dashboard.html)

**Sister project (private):** *Azalyst Alpha Quant Research* — the private futures-grade quantitative research engine this project feeds into.

**Maintained by:** [@gitdhirajsv](https://github.com/gitdhirajsv)

---

## What This Is

Azalyst Birdeye is a **three-engine signal platform** that continuously scans Solana + EVM DEX activity for actionable patterns:

1. **Quant Signal Engine** — rule-based + anomaly scoring over trending tokens, top traders, holder distribution, and trade aggregates. Commits a structured report every 15 minutes.
2. **NIM Qwen Agent** — a ReAct LLM agent (NVIDIA NIM / Qwen 2.5-Coder 32B) that autonomously invokes Birdeye tools and writes narrative reports on-demand or on schedule.
3. **Behavioral ML Pipeline** — wallet clustering + frequent-subsequence mining (PrefixSpan) + supervised LightGBM classifier that learns sequences like `whale_buy → anonymous_buy × N → pump` and scores each fresh signal with a calibrated probability.

All three write to the same SQLite database (`data/birdeye_quant.db`) and report directory (`reports/`) which is committed back to the repo after each run, so the **dashboard is a static page** that reads directly from the GitHub API.

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
                   AZALYST BIRDEYE — v1.0 SIGNAL STACK

  DATA SOURCE              INGESTION                 STORAGE
 Birdeye Public API    BirdeyeClient (retry 429+5xx)  SQLite (WAL)
 18+ endpoints         Token + trader + trade aggs    6 base tables
 9 chains              3-level retry, 1.5s jitter     5 ML tables
 REST polling          Rate-limited serial writes     Committed in repo

  QUANT ENGINE            LLM AGENT                 ML PIPELINE
 Rule + anomaly score   NIM Qwen 2.5-Coder 32B      Wallet clustering
 Pump / dump / risk     ReAct loop (15 iter cap)    PrefixSpan mining
 Smart-money detection  Tool dispatch via JSON      LightGBM classifier
 Binance USDT filter    Reports to markdown         ml_prob per snapshot

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
| `quant_signal_engine.yml` | `*/15 * * * *` (every 15 min) | Multi-chain scan → emit signals → evaluate mature ones |
| `agent.yml` | `*/15 * * * *` | NIM Qwen ReAct agent runs `daily_scan` + writes markdown reports |
| `ml_pipeline.yml` | `17 */2 * * *` + `13 3 * * *` | 2-hourly **refresh** (cluster→events→mine→score→export); daily **retrain** at 03:13 UTC |
| Dashboard | static | GitHub Pages — redeploys on every commit to `main` |

All write workflows share the `birdeye-quant-signal-engine` concurrency group so DB/report writes are serialized end-to-end.

---

## Quick Start

### Run on GitHub Actions (recommended)

1. Fork this repository.
2. Add two repository secrets: `BIRDEYE_API_KEY` (required) and `NIM_API_KEY` (required for the LLM agent — free tier available at [build.nvidia.com](https://build.nvidia.com)).
3. Enable GitHub Actions on the fork. Workflows will begin firing within 15 minutes.
4. Open `https://<your-handle>.github.io/Azalyst-Birdeye-Scanner/dashboard.html?repo=<your-handle>/Azalyst-Birdeye-Scanner` — the dashboard reads your fork's data.

No cloud servers, no cron box, no database to manage. Runners have 7GB RAM / 2 CPU / 14GB disk — ample for LightGBM + PrefixSpan on the committed SQLite database.

### Local Runs (development)

```bash
pip install -r requirements.txt

# Multi-chain scan → writes reports/latest_quant_signals.json + SQLite
python quant_signal_engine.py scan --chains "solana,base,ethereum,arbitrum,bnb" \
  --limit 20 --trade-limit 50 --evaluate \
  --outcome-horizon-min 60 --outcome-target-pct 10

# LLM agent — ReAct loop over Birdeye tools
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
| **sniper** | *(reserved — requires real on-chain creation timestamps; not active in v1)* |
| **anonymous** | Everything else (the default bucket) |

Back-fills from `top_traders.raw_json` when legacy rows have zero structured columns — fixes an upstream ingestion bug where `volume` was being mapped in place of `volumeUsd`.

### Frequent-Subsequence Mining

For each snapshot, all `wallet_events` in the 30-minute lookback are serialized into a `(cluster, action)` token sequence, e.g.:

```
["whale_buy", "anonymous_buy", "anonymous_buy", "smart_money_buy", "anonymous_buy"]
```

PrefixSpan mines **frequent subsequences** (min support 5, length 2–4) across all tokens, then ranks them by **lift** against the `signal_outcomes.is_true` label. The top-40 patterns land in `pattern_library`; per-snapshot matches in `pattern_matches`.

Falls back to frequent-bigram counting if the `prefixspan` package isn't installed — the pipeline always completes.

### Supervised Classifier

| Parameter | Value |
|---|---|
| **Primary model** | LightGBM (`n_estimators=300`, `lr=0.05`, `num_leaves=31`, `class_weight=balanced`) |
| **Fallback** | sklearn `GradientBoostingClassifier` |
| **Target** | `signal_outcomes.is_true` (binary, horizon = 60 min, target = 10% move) |
| **Features** | Token metrics · heuristic scores · trade-aggs ratios · 10 cluster-action counts · binary pattern indicators |
| **Train/val split** | 80/20 stratified, `random_state=42` |
| **Min samples** | 50 labeled rows (refuses to train below — graceful cold-start) |
| **Artifacts** | `ml/model.pkl`, `ml/metrics.json` |
| **Validation metrics** | ROC AUC · precision · recall · F1 |

### Prediction → ML Signal

Each snapshot receives:

| Field | Value |
|---|---|
| `ml_prob` | Predicted probability of hitting target (0–1) |
| `ml_direction` | `up` (≥ 0.55), `down` (≤ 0.45), or `flat` |
| `model_version` | Training timestamp of the producing model |

Scores land in `ml_scores` (keyed on `snapshot_id`) and the corresponding columns on `signals`. The ML tab on the dashboard surfaces the top-25 ML-ranked signals from the last 24h plus the pattern library.

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

Labels are applied via hysteresis across the score space: `pump_candidate`, `whale_accumulation`, `dump_risk`, `anomaly_watch`, `rug_risk`.

### Outcome Evaluation

`signal_outcomes` closes the loop — every scan also re-checks mature prior signals (age ≥ 60 min) and writes:

```
entry_price  current_price  return_pct  is_true  (↑ 10% within horizon? 1 : 0)
```

This `is_true` column is what the LightGBM classifier consumes as its training label. Ground truth is free and continuously accumulating.

### Binance-Only Filter

`--binance-usdt-only` flag narrows the final report to tokens with a corresponding Binance USDT-futures listing, matching the execution universe of the sister project (*Azalyst Alpha Quant Research*).

---

## NIM Qwen Agent

A from-scratch ReAct loop (no LangChain, no framework) wired to 21 tools covering file I/O, shell, and 15 Birdeye endpoints.

| Parameter | Value |
|---|---|
| **Model** | `qwen/qwen2.5-coder-32b-instruct` via NVIDIA NIM |
| **Loop** | Think → Tool → Observe → Repeat |
| **Iteration cap** | 15 |
| **Temperature** | 0.1 |
| **Tool format** | Triple-backtick `tool_call` blocks containing JSON `{tool, args}` |
| **Early exit** | `Final Answer:` sentinel in model output |
| **Fail-safe** | Aborts after 5 iterations with no tool call or final answer |

### Available Tools

`bash`, `read_file`, `write_file`, `list_dir`, `search`, `track_whale`, `find_pumps`, `analyze_token`, `daily_scan`, `get_profitable_traders`, `get_wallet_pnl`, `get_top_traders`, `check_token_security`, `get_new_listings`, `get_token_creation_info`, `get_holder_list`, `get_wallet_pnl_details`, `get_trader_txs`, `get_ohlcv`, `get_wallet_token_list`, `get_wallet_tx_list`.

Workflow invokes the agent on schedule (every 15 min), on dispatch (custom task via GitHub UI), or via `/agent <task>` issue comments.

---

## Data & Storage

### Database Schema

SQLite in WAL mode at `data/birdeye_quant.db`. Core tables populated by the quant engine:

| Table | Purpose |
|---|---|
| `tokens` | Distinct tokens seen, keyed on `(chain, address)` |
| `token_snapshots` | One row per token per scan — price, volume, holders, security flags |
| `trade_aggs` | Buy/sell counts + whale buy/sell volume per snapshot |
| `top_traders` | Per-wallet PnL/volume observed at each snapshot |
| `signals` | Scored snapshots — pump/dump/anomaly/smart-money/risk + label |
| `signal_outcomes` | Closed-loop evaluation — entry/current price, return_pct, is_true |

ML pipeline extends the schema (additive, idempotent DDL):

| Table | Purpose |
|---|---|
| `wallet_clusters` | `(wallet, cluster, pnl_total_usd, volume_total_usd, snapshots_seen, win_rate)` |
| `wallet_events` | Synthesized `(snapshot_id, wallet, cluster, action, size_usd, size_bucket)` |
| `pattern_library` | Mined subsequences — `(prefix_json, length, support, lift, positive_rate)` |
| `pattern_matches` | Join of snapshots → matched patterns |
| `ml_scores` | `(snapshot_id, ml_prob, ml_direction, model_version)` |

`signals.ml_prob` and `signals.ml_direction` columns are added via idempotent `ALTER TABLE` on schema init.

### Reports Directory

| File | Writer | Consumer |
|---|---|---|
| `reports/latest_quant_signals.{json,csv}` | Quant engine | Dashboard — Intelligence tab |
| `reports/latest_quant_outcomes.{json,csv}` | Quant engine | Dashboard — Feed tab |
| `reports/latest_quant_brief.md` | Qwen brief mode | Human review |
| `reports/latest_ml_scores.json` | ML export | Dashboard — ML tab |
| `reports/quant_signals_<ts>.{json,csv}` | Quant engine (historical) | Archive |
| `reports/daily_scan.md` | NIM Qwen Agent | Human review |

All report files are force-added by workflows and committed back to `main` after each run.

---

## Dashboard

Static single-page app at `dashboard.html`, deployed via GitHub Pages. Uses the GitHub REST API directly — no backend, no build step, no auth required for public repos.

### Tabs

| Tab | Shows |
|---|---|
| **Intelligence** | Pump signals · dump warnings · whale moves · gems · chain pulse |
| **Traders** | Per-snapshot top-trader leaderboard by PnL |
| **Whales** | Observed wallet PnL summaries + watchlist updates |
| **Gems** | New/low-cap tokens with pump signals and LP stats |
| **Security** | Rug risk (mintable, freeze authority, concentration) |
| **ML** *(new)* | Model status · ROC AUC · cluster breakdown · top ML signals · pattern library by lift |
| **Chain Map** | Pump/dump heat per chain |
| **Live Feed** | Interleaved signal stream |
| **Reports** | Browse all committed reports |
| **System** | Workflow run health — SKIPPED runs excluded from ops-rate |

---

## Repository Structure

```
Azalyst-Birdeye-Scanner/
│
├── quant_signal_engine.py        # Rule + anomaly scoring, outcome evaluation
├── agent.py                      # NIM Qwen ReAct loop (canonical — repo root)
├── tools.py                      # 21-tool dispatcher for the agent
├── birdeye_tracker.py            # Multi-chain Birdeye API wrapper (9 chains)
├── example_whale_tracking.py     # Standalone usage examples
│
├── agent/                        # Back-compat shims (importlib) that load root
│   ├── agent.py                  #   Shim → root agent.py
│   ├── tools.py                  #   Shim → root tools.py
│   └── birdeye_tracker.py        #   Shim → root birdeye_tracker.py
│
├── ml/                           # Behavioral ML pipeline
│   ├── __main__.py               #   CLI: schema|cluster|events|mine|train|score|export|all|refresh
│   ├── schema.py                 #   Additive DDL for ML tables + ALTER signals
│   ├── clustering.py             #   Wallet → {whale, smart_money, mm, anonymous}
│   ├── events.py                 #   Synthesize wallet_events from top_traders
│   ├── patterns.py               #   PrefixSpan frequent-subsequence mining
│   ├── features.py               #   Feature matrix (token + cluster + pattern features)
│   ├── train.py                  #   LightGBM primary, sklearn GBT fallback
│   ├── score.py                  #   Apply model → ml_scores + signals.ml_prob
│   ├── export.py                 #   Emit reports/latest_ml_scores.json for dashboard
│   ├── model.pkl                 #   Trained classifier (committed after retrain)
│   └── metrics.json              #   Validation metrics from last retrain
│
├── .github/workflows/
│   ├── quant_signal_engine.yml   #   Every 15 min — scan + evaluate
│   ├── agent.yml                 #   Every 15 min — NIM Qwen ReAct run
│   └── ml_pipeline.yml           #   2-hourly refresh + daily retrain
│
├── dashboard.html                # Static SPA — reads GH API, no backend
├── AGENTS.md                     # Agent system prompt
├── requirements.txt              # Python dependencies
├── SETUP_INSTRUCTIONS.md         # Fork-and-run guide
├── README.md                     # This file
│
├── data/
│   └── birdeye_quant.db          # SQLite (WAL) — committed, read by dashboard indirectly
├── reports/                      # JSON/CSV/MD exports (committed by workflows)
└── .qwen/                        # Qwen Code settings
```

---

## Technical Specifications

| Parameter | Value |
|---|---|
| **Language** | Python 3.11 |
| **Runtime** | GitHub Actions (`ubuntu-latest`, 7GB RAM / 2 CPU / 14GB disk) |
| **Data source** | Birdeye Public API (`https://public-api.birdeye.so`) |
| **HTTP client** | `requests` with 3-retry on 429 + 5xx + network errors, 1.5s jittered backoff |
| **Rate limiting** | Serial calls, 0.25s min delay between requests |
| **Storage** | SQLite with WAL, committed to repo as `data/birdeye_quant.db` |
| **LLM** | NVIDIA NIM Qwen 2.5-Coder 32B, temperature 0.1 |
| **ML primary** | LightGBM 4.1+ |
| **ML fallback** | sklearn GradientBoostingClassifier |
| **Sequence mining** | `prefixspan` 0.5+, bigram fallback |
| **Feature count** | ~65 numeric features per snapshot (token + aggs + cluster + pattern) |
| **Lookback window** | 30 min (wallet-event window for pattern matching) |
| **Outcome horizon** | 60 min default (tunable via `--outcome-horizon-min`) |
| **Outcome target** | 10% price move (tunable via `--outcome-target-pct`) |
| **Retrain cadence** | Daily 03:13 UTC, minimum 50 labeled samples |
| **Score cadence** | Every 2 hours at `:17` past (recent) + daily full re-score after retrain |
| **Concurrency** | All write-workflows share `birdeye-quant-signal-engine` group |
| **Universe** | 9 chains, Birdeye trending + top-traders per chain |

---

## Birdeye Endpoints Integrated

| Category | Endpoints |
|---|---|
| **Discovery** | `/defi/trending_tokens/{chain}`, `/defi/token_trending`, `/defi/v2/tokens/new_listing` |
| **Token detail** | `/defi/token_overview`, `/defi/token_security`, `/defi/token_creation_info`, `/defi/v3/token/holder` |
| **Market data** | `/defi/v3/ohlcv`, `/defi/v3/pair/overview/single`, `/defi/v3/pair/overview/multiple`, `/defi/txs/token` |
| **Traders** | `/defi/v2/tokens/top_traders`, `/trader/gainers-losers`, `/trader/txs/seek_by_time` |
| **Wallets** | `/wallet/v2/pnl/summary`, `/wallet/v2/pnl/details`, `/v1/wallet/token_list`, `/v1/wallet/tx_list` |

---

## Research Principles

- **Ground-truth labels** — every signal is evaluated against realized price movement; `is_true` is not synthetic
- **Graceful cold-start** — ML refuses to train below 50 labeled samples; pipeline never fails for want of data
- **No hidden state** — all data (SQLite, reports, models) committed to the repo, fully auditable
- **Reproducible** — same code, same data, same output; workflows are deterministic given Birdeye's state
- **Rate-limit respectful** — 3-retry backoff on 429/5xx, serialized writes, zero parallel requests against Birdeye
- **Additive ML** — new ML tables never replace existing scoring; heuristic scores remain available as features
- **Transparency** — `model_metrics` JSON exports ROC AUC, precision, recall, F1, top feature importances every retrain
- **Evidence over claims** — the dashboard shows model health and pattern lift; no performance is claimed that isn't visible

---

## Operational Notes

### Secrets Required

| Secret | Purpose | Where to get |
|---|---|---|
| `BIRDEYE_API_KEY` | All data ingestion | [bds.birdeye.so](https://bds.birdeye.so) — free tier available |
| `NIM_API_KEY` | NIM Qwen agent | [build.nvidia.com](https://build.nvidia.com) — free tier available |

Workflow fails loudly with `::error::` annotations if either is missing — no silent no-op iterations.

### Concurrency

All write-workflows share `concurrency: birdeye-quant-signal-engine` with `cancel-in-progress: false`. This serializes SQLite writes and git pushes — concurrent runs queue cleanly rather than racing.

### Runtime Budget

| Workflow | Typical duration | Hard timeout |
|---|---|---|
| Quant scan (2 chains, limit 20) | 90–200s | 15 min |
| Quant scan (multi-chain, limit 12) | 200–600s | 15 min |
| NIM Qwen agent (daily_scan) | 30–90s | 15 min |
| ML refresh | 30–90s | 30 min |
| ML full + retrain | 60–180s | 30 min |

Free GitHub Actions minutes on public repos are unlimited — the whole stack is zero operating cost at current cadence.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| **Agent runs SKIPPED on schedule** | Check `agent.yml` job-level `if:` includes `github.event_name == 'schedule'`. Fixed in v1.0. |
| **`NIM_API_KEY`/`BIRDEYE_API_KEY` secret missing** | Workflow now fails fast with `::error::` rather than iterating on `None`. |
| **`top_traders` rows all zero** | Pre-v1.0 ingestion bug — ML pipeline back-fills from `raw_json` automatically. New rows ingest correctly. |
| **ML tab empty on dashboard** | Pipeline not yet run — first scheduled fire is at `:17` past every 2nd hour. Trigger manually via `gh workflow run ml_pipeline.yml`. |
| **Dashboard ops-rate shows low %** | Pre-v1.0: skipped Agent runs counted as failures. Fixed — SKIPPED is excluded from health rate. |
| **Training fails with "insufficient_data"** | Need ≥ 50 rows in `signal_outcomes` with `is_true IS NOT NULL`. Usually crosses threshold within 2–3 days of continuous scanning. |
| **Git push conflicts on workflow commit** | `git pull --rebase origin main` before push is built into every workflow step. Shouldn't surface — if it does, check concurrency group. |
| **PrefixSpan not installed** | Falls back to frequent-bigram counting — pipeline still completes, patterns just shorter. |
| **Rate-limited by Birdeye** | Free-tier key is required; anonymous hits are aggressively throttled. 429s are retried 3× with jittered backoff. |

---

## Version History

| Version | Date | Key Changes |
|---|---|---|
| **v0.x** | Q1 2026 | Initial multi-chain tracker — NIM Qwen agent + rule-based signals |
| **v1.0** | Apr 2026 | **Current** — schedule guard fix, behavioral ML pipeline, `top_traders` ingestion fix, dashboard ML tab, concurrency-grouped workflows, 5xx retry, duplicate-module dedupe |

---

## Roadmap

| Priority | Item | Status |
|---|---|---|
| ● | Real-time wallet tx ingestion via `/trader/txs/seek_by_time` (replace synthesized events) | not started |
| ● | Birdeye websocket subscriptions on tracked wallets | not started |
| ● | True on-chain token creation timestamps → enable sniper cluster | not started |
| ○ | Birdeye MCP Server integration — replace hand-rolled ReAct with MCP tool-use | not started |
| ○ | Historical price backfill via `/defi/history_price` for proper backtesting | not started |
| ○ | Regression head (expected `return_pct`) alongside the binary classifier | not started |
| ○ | Telegram/Discord alerting on high-confidence ML signals | not started |

---

## Related Projects

| Project | Visibility | Purpose |
|---|---|---|
| **Azalyst Birdeye Alpha Signal Engine** (this repo) | Public | Real-time on-chain signal platform |
| [Azalyst Alpha Research Engine](https://github.com/gitdhirajsv/Azalyst-Alpha-Research-Engine) | Public | OHLCV-based quantitative research — 77-week OOS walk-forward |
| **Azalyst Alpha Quant Research** | Private | Futures-grade quant research, the execution layer this project feeds |

---

## Disclaimer

This is a research and educational project. **Not financial advice.** On-chain signals, pump/dump detections, and ML probabilities are observations, not recommendations. Do your own research. Past on-chain behavior does not guarantee future price movement. Use at your own risk.

---

<div align="center">

**v1.0** | Built by [Azalyst](https://github.com/gitdhirajsv) | *Azalyst Alpha Quant Research*

*"Evidence over claims. Always."*

</div>
