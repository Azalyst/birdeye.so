# Azalyst — Multi-Chain Whale Tracking Agent

Automated on-chain intelligence across 9 chains. Runs on GitHub Actions. Scans every 4 hours, commits structured reports, and surfaces pump/dump signals for manual review via a monitoring dashboard.

**Dashboard:** [azalyst.github.io/birdeye.so/dashboard.html](https://azalyst.github.io/birdeye.so/dashboard.html?repo=Azalyst/birdeye.so)

**Maintained by:** [@gitdhirajsv](https://github.com/gitdhirajsv)

---

## Chains Supported

| Chain | Identifier |
|---|---|
| Solana | `solana` |
| Ethereum | `ethereum` |
| Base | `base` |
| Arbitrum | `arbitrum` |
| BNB Chain | `bnb` |
| Avalanche | `avalanche` |
| Polygon | `polygon` |
| Optimism | `optimism` |
| zkSync | `zksync` |

---

## Architecture

```
GitHub Actions
  ├── agent.yml              — On-demand agent (workflow_dispatch + issue comments)
  └── whale_tracking.yml     — Scheduled scans (cron: 0 */4 * * *)

agent/
  ├── agent.py               — ReAct loop: Think → Tool → Observe → Repeat (15 iter cap)
  ├── tools.py               — Tool dispatcher with chain routing
  └── birdeye_tracker.py     — Birdeye API wrapper, signal logic, multi-chain

reports/                     — Scan output, auto-committed after each run
dashboard.html               — Operational monitoring UI (GitHub Pages)
```

---

## Dashboard

**Live:** [azalyst.github.io/birdeye.so/dashboard.html](https://azalyst.github.io/birdeye.so/dashboard.html?repo=Azalyst/birdeye.so)

The dashboard reads directly from the GitHub API. No backend, no server. What it shows:

- **System status** — last run result, success rate across last 10 runs, next scheduled scan time
- **Workflow run history** — every agent and whale tracker run with timestamp, trigger, duration, and pass/fail
- **Activity feed** — chronological log of all agent events
- **Report browser** — list of all files in `reports/`, click any to read contents inline

For private repositories, add a GitHub Personal Access Token in the dashboard Config panel. It is stored in memory only and never persisted or transmitted anywhere other than the GitHub API.

---

## Setup

### Secrets

`Settings → Secrets and variables → Actions → New repository secret`

| Secret | Required | Get From |
|---|---|---|
| `NIM_API_KEY` | Yes | [build.nvidia.com](https://build.nvidia.com) — free tier |
| `BIRDEYE_API_KEY` | Recommended | [birdeye.so](https://birdeye.so) — free tier |

### Actions Permissions

`Settings → Actions → General → Workflow permissions → Read and write permissions`

Required so the bot can commit scan reports back to the repository.

### Dependencies

```bash
pip install -r requirements.txt
```

---

## Usage

### Scheduled (Automatic)

Whale tracking runs every 4 hours with no intervention. Reports saved and committed to `reports/` automatically.

### On-Demand — GitHub Actions UI

`Actions → NIM Qwen Agent → Run workflow`

```
daily_scan
daily_scan chains=["solana","ethereum"]
find_pumps chain=ethereum
analyze_token token_address=<ADDRESS> chain=base
track_whale wallet_address=<ADDRESS> chain=arbitrum
```

### On-Demand — Issue Comment

```
/agent daily_scan
/agent find_pumps chain=solana
/agent analyze_token token_address=<ADDRESS> chain=ethereum
/agent track_whale wallet_address=<ADDRESS> chain=bnb
/agent daily_scan chains=["solana","base","arbitrum"]
```

### Local

```bash
export NIM_API_KEY=your_key
export BIRDEYE_API_KEY=your_key

python agent/agent.py "daily_scan chains=['solana','ethereum']"
python example_whale_tracking.py daily
python example_whale_tracking.py pumps
python example_whale_tracking.py track <WALLET> <CHAIN>
python example_whale_tracking.py analyze <TOKEN> <CHAIN>
```

### Quant Signal Engine

For continuous data collection and ML-style pump/dump scoring, run the direct quant scanner:

```bash
python quant_signal_engine.py scan --chains all --limit 40 --binance-usdt-only
python quant_signal_engine.py loop --chains all --limit 40 --interval 300 --binance-usdt-only
python quant_signal_engine.py signals --show 50
python quant_signal_engine.py evaluate --horizon-min 60 --target-pct 10
```

It stores every snapshot in `data/birdeye_quant.db` and writes ranked JSON/CSV reports to `reports/`.
The main production mode now scans all supported Birdeye chains but only keeps symbols that match the live Binance USDT futures universe, with a minimum on-chain liquidity floor so the dashboard focuses on names you can actually trade instead of same-symbol dust tokens.
GitHub Actions runs `.github/workflows/quant_signal_engine.yml` every 15 minutes when `BIRDEYE_API_KEY` is configured as a repository secret. When `chains=all`, the scheduler rotates through 3 chain batches so runtime stays fast while still covering the full universe, and it can fall back to a committed Binance futures cache if the runner cannot reach Binance directly. Optional `NIM_API_KEY` enables a Qwen analyst brief.
See `QUANT_SIGNAL_ENGINE.md` for the full workflow.

---

## Tools

### Core

| Tool | Args | Description |
|---|---|---|
| `bash` | `cmd` | Run shell command in Actions runner |
| `read_file` | `path` | Read file from repository |
| `write_file` | `path`, `content` | Write file |
| `list_dir` | `path` | Directory listing, 3 levels deep |
| `search` | `pattern`, `path` | grep -rn across repository |

### Birdeye / On-Chain

All Birdeye tools accept an optional `chain` parameter. Default is `solana`.

| Tool | Key Args | Output | Endpoint |
|---|---|---|---|
| `find_pumps` | `chain` | Top 10 scored candidates (0-100) | `/defi/trending_tokens` |
| `analyze_token` | `token_address`, `chain` | Signal type, confidence %, indicators | `/defi/token_overview` |
| `track_whale` | `wallet_address`, `chain` | Portfolio breakdown, top holdings | `/v1/wallet/token_list` |
| `daily_scan` | `chains` (list, optional) | Full report across all specified chains | Multiple |
| `get_profitable_traders` | `chain`, `time_frame` | Top 20 traders by PnL, volume, trades | `/trader/gainers-losers` |
| `get_wallet_pnl` | `wallet_address`, `chain` | Realized/unrealized PnL, win rate | `/wallet/v2/pnl/summary` |
| `get_top_traders` | `token_address`, `chain` | Top 10 traders per token by volume | `/defi/v2/tokens/top_traders` |
| `check_token_security` | `token_address`, `chain` | Rug risk score, mint/freeze flags | `/defi/token_security` |
| `get_new_listings` | `chain`, `limit` | Freshly listed tokens with age | `/defi/v2/tokens/new_listing` |
| `get_token_creation_info` | `token_address`, `chain` | Deployer, creation time, initial supply | `/defi/token_creation_info` |
| `get_holder_list` | `token_address`, `chain` | Top holders with balance % | `/defi/v3/token/holder` |
| `get_wallet_pnl_details` | `wallet_address`, `chain` | Token-by-token PnL breakdown | `/wallet/v2/pnl/details` |
| `get_trader_txs` | `wallet_address`, `chain` | Trade history with time filtering | `/trader/txs/seek_by_time` |
| `get_ohlcv` | `token_address`, `timeframe` | Candle data (1s-1d intervals) | `/defi/v3/ohlcv` |
| `get_wallet_token_list` | `wallet_address`, `chain` | Current holdings with USD values | `/v1/wallet/token_list` |
| `get_wallet_tx_list` | `wallet_address`, `chain` | Full transaction history | `/v1/wallet/tx_list` |

`daily_scan` with no `chains` argument scans all 9 supported chains.

---

## Signal Methodology

### Pump Indicators

| Signal | Threshold |
|---|---|
| Smart wallet accumulation | 3+ whale addresses buying |
| Volume spike | 10x the hourly average in 1 hour |
| Holder growth | 500+ new holders in 24 hours |
| LP stability | Liquidity unchanged or growing |
| Distribution | Top 10 holders below 30% |

### Dump Indicators

| Signal | Threshold |
|---|---|
| Whale outflows | Sell volume exceeds buy volume 2:1 |
| LP contraction | Liquidity drops more than 20% |
| Holder exodus | Holder count declining 100+ in 24h |
| Dev activity | Owner wallet executing sells |
| Concentration | Top 10 holders above 50% |

### Confidence

Ratio of triggered indicators to total possible (0-100%). Above 70% is a strong signal. 40-70% requires confirmation. Below 40% is informational.

**Signals are for manual review only. The system does not execute trades.**

### Hidden Gem Filters

Applied before scoring in `find_pumps`:

| Filter | Value |
|---|---|
| Token age | Under 24 hours |
| Minimum liquidity | $2,000 |
| Minimum 1-hour volume | $10,000 |
| Mintable | No |
| Top 10 holder concentration | Below 50% |

Scoring: volume spike (30 pts) + holder growth (30 pts) + liquidity (20 pts) + security (20 pts).

---

## Reports

Each scan saves to `reports/` using the naming convention:

```
reports/whale_scan_YYYYMMDD_HHMMSS.txt
reports/daily_scan_YYYYMMDD_HHMMSS.md
reports/daily_scan_YYYYMMDD_HHMMSS.json    — Structured JSON with full data
reports/profitable_traders_YYYYMMDD.json   — Trader leaderboard
```

Committed automatically by `github-actions[bot]` after every successful run. Readable in the dashboard report browser without leaving the page.

---

## New Features (Latest Update)

### Trader Leaderboard
Get top profitable traders across chains with PnL, volume, and trade counts.

```tool_call
{"tool": "get_profitable_traders", "args": {"chain": "ethereum", "time_frame": "7D"}}
```

### Wallet PnL Tracking
Track realized and unrealized profits for any wallet.

```tool_call
{"tool": "get_wallet_pnl", "args": {"wallet_address": "0x...", "chain": "ethereum"}}
```

### Top Traders Per Token
Find the most active traders for specific tokens.

```tool_call
{"tool": "get_top_traders", "args": {"token_address": "0x...", "chain": "base", "time_frame": "24h"}}
```

### Token Security Checks
Pre-filter risky tokens before scoring. Flags mintable supply, freeze authority, and holder concentration.

```tool_call
{"tool": "check_token_security", "args": {"token_address": "0x...", "chain": "solana"}}
```

### Enhanced Daily Scan
Now includes profitable traders per chain, security alerts, and wallet PnL enrichment. Saves structured JSON reports.

```tool_call
{"tool": "daily_scan", "args": {"chains": ["solana", "ethereum", "base"]}}
```

### Improved Dashboard
New tabs: **Traders** (leaderboard), **Security** (rug risk alerts), **Whales** (PnL panel). Dark theme with green (#00ff88) profits and red (#ff4466) losses.

---

## Costs

| Service | Cost |
|---|---|
| GitHub Actions | Free (public repo: unlimited minutes) |
| GitHub API | Free (60 req/hr unauthenticated, 5,000 with token) |
| NVIDIA NIM | Free tier with signup credits |
| Birdeye API | Free tier available, no credit card required |

Private repo Actions minutes: 2,000 free/month. At 6 runs/day x ~2 min each = ~360 min/month, within the free tier.

---

## Agent Loop

```
Thought   →  parse task, identify required tool
Action    →  emit tool_call JSON
Observe   →  receive tool output
Repeat    →  until Final Answer or 15-iteration cap
```

Tool calls execute first on every iteration. Final Answer check runs only after confirming no tool call is present. The loop aborts with a diagnostic message if neither a tool call nor a Final Answer is produced after 5 iterations.

---

## Security

- API keys stored as encrypted GitHub Secrets, injected at runtime, never logged or committed
- All issue and PR comment content treated as untrusted input
- Dashboard connects to GitHub API only — no third-party data transmission
- Agent will not run destructive git operations without explicit instruction

---

## Troubleshooting

**Reports contain placeholder text instead of real data**
Fixed in current `agent.py`. The original code had a logic inversion where the Final Answer check ran before tool dispatch, making tools unreachable.

**Birdeye tools return empty results**
Verify `BIRDEYE_API_KEY` is set in repository secrets. Without a key, public endpoints are rate-limited aggressively. Test locally: `python example_whale_tracking.py daily`.

**Workflow fails with permission error**
`Settings → Actions → General → Workflow permissions → Read and write permissions`.

**Dashboard shows no data**
Enter repo as `owner/repository` exactly (case-sensitive). For private repos, add a GitHub PAT in the Config panel.

---

## File Reference

```
.
├── .github/workflows/
│   ├── agent.yml                  — On-demand agent
│   └── whale_tracking.yml         — Scheduled scans
├── agent/
│   ├── agent.py                   — ReAct loop
│   ├── tools.py                   — Tool dispatcher
│   └── birdeye_tracker.py         — Birdeye + signal logic (multi-chain)
├── reports/                       — Auto-committed scan output
├── dashboard.html                 — Monitoring UI
├── example_whale_tracking.py      — Local test runner
├── requirements.txt               — Python dependencies
├── AGENTS.md                      — Agent behavior spec
├── BIRDEYE_USAGE.md               — Birdeye workflow reference
└── README.md                      — This file
```

---

## Disclaimer

This system is for informational and educational purposes only. Signals are heuristic-based and have not been backtested. Past signal performance does not predict future results. Do not make investment decisions based solely on this output. Manage risk independently.

---

*Powered by [Birdeye](https://birdeye.so) and [NVIDIA NIM](https://build.nvidia.com).*
