# Azalyst ETF Intelligence — Whale Tracking Agent

Automated on-chain intelligence system for Solana. Runs on GitHub Actions. No external services required beyond API keys. Scans every 4 hours, saves structured reports, and exposes a monitoring dashboard for operational visibility.

---

## Architecture

```
GitHub Actions
  ├── agent.yml              — On-demand agent (workflow_dispatch + issue comments)
  └── whale_tracking.yml     — Scheduled scans (every 4 hours, cron: 0 */4 * * *)

agent/
  ├── agent.py               — ReAct loop: Think → Tool → Observe → Repeat
  ├── tools.py               — Tool dispatcher (bash, file I/O, Birdeye)
  └── birdeye_tracker.py     — Birdeye API wrapper + signal logic

reports/                     — Scan output committed automatically after each run
dashboard.html               — Operational monitoring UI (GitHub Pages compatible)
```

The agent operates as a ReAct loop with a 15-iteration cap. On each iteration it either executes a tool call or emits a Final Answer. Tool results are fed back as observations. All workflow output is committed to `reports/` by the bot.

---

## Setup

### 1. Repository Secrets

Navigate to `Settings → Secrets and variables → Actions → New repository secret`.

| Secret | Required | Source |
|---|---|---|
| `NIM_API_KEY` | Yes | [build.nvidia.com](https://build.nvidia.com) |
| `BIRDEYE_API_KEY` | Recommended | [birdeye.so](https://birdeye.so) |

Without `BIRDEYE_API_KEY` the agent will run but Birdeye API calls will be rate-limited or unauthenticated.

### 2. Actions Permissions

`Settings → Actions → General → Workflow permissions → Read and write permissions`

Required for the bot to commit scan reports back to the repository.

### 3. Install Dependencies (local)

```bash
pip install -r requirements.txt
```

```
openai>=1.0.0
python-dotenv
requests>=2.31.0
```

---

## Usage

### Scheduled (Automatic)

The whale tracking workflow runs every 4 hours without any intervention. Reports are saved to `reports/` and committed automatically.

### On-Demand via GitHub Actions UI

`Actions → NIM Qwen Agent → Run workflow → Enter task`

Example tasks:
```
daily_scan and save results to reports/scan_manual.md
find_pumps
analyze_token token_address=<ADDRESS>
track_whale wallet_address=<ADDRESS>
```

### On-Demand via Issue Comment

Post a comment on any issue in the repository:

```
/agent daily_scan
/agent find_pumps
/agent analyze_token token_address=<ADDRESS>
/agent track_whale wallet_address=<ADDRESS>
```

```
/whale daily
/whale find_pumps
/whale analyze_token
```

The bot will respond with a comment linking to the workflow run.

### Local

```bash
export NIM_API_KEY=your_key
export BIRDEYE_API_KEY=your_key   # optional

python agent/agent.py "daily_scan and save results to reports/test.md"
python example_whale_tracking.py daily
python example_whale_tracking.py pumps
python example_whale_tracking.py track <WALLET_ADDRESS>
python example_whale_tracking.py analyze <TOKEN_ADDRESS>
```

---

## Available Tools

The agent selects tools autonomously based on the task. All tools are defined in `agent/tools.py`.

### Core

| Tool | Description |
|---|---|
| `bash(cmd)` | Run any shell command in the Actions runner |
| `read_file(path)` | Read a file from the repository |
| `write_file(path, content)` | Write or overwrite a file |
| `list_dir(path)` | List directory contents up to 3 levels |
| `search(pattern, path)` | grep -rn across the repository |

### Birdeye / On-Chain

| Tool | Description | Key Output |
|---|---|---|
| `find_pumps()` | Scans trending tokens for early pump signals | Top 10 scored 0–100 |
| `analyze_token(token_address)` | Deep pump/dump signal analysis for a single token | Signal type, confidence %, indicators |
| `track_whale(wallet_address)` | Adds wallet to watchlist, returns portfolio breakdown | Holdings, top tokens, recent activity |
| `daily_scan()` | Full workflow: trending analysis + whale trades + hidden gems + watchlist | Formatted report |

---

## Signal Methodology

### Pump Indicators (Green Flags)

| Signal | Threshold |
|---|---|
| Smart wallet accumulation | 3+ distinct whale addresses buying |
| Volume spike | 10x relative to 24h average in 1 hour |
| Holder growth | 500+ new holders in 24 hours |
| LP stability | Liquidity pool unchanged or growing |
| Distribution | Top 10 holders below 30% concentration |

### Dump Indicators (Red Flags)

| Signal | Threshold |
|---|---|
| Whale outflows | Large sell volume exceeds buy volume 2:1 |
| LP contraction | Liquidity drops more than 20% |
| Holder exodus | Holder count declining |
| Dev activity | Owner wallet executing sells |
| Concentration | Top 10 holders above 50% |

### Confidence Scoring

Confidence is the ratio of triggered indicators to total possible indicators (0–100%). A score above 70% is considered a strong signal in either direction. Between 40–70% requires additional confirmation. Below 40% is informational only.

**This system surfaces candidates for manual review. It does not execute trades, manage positions, or provide financial advice.**

---

## Hidden Gem Filters

`find_pumps()` applies the following filters before scoring:

| Filter | Value |
|---|---|
| Token age | Under 24 hours |
| Minimum liquidity | $2,000 |
| Minimum 1-hour volume | $10,000 |
| Mintable | No |
| Top 10 holder concentration | Below 50% |

Scoring weights: volume spike (30 pts), holder growth (30 pts), liquidity strength (20 pts), security checks (20 pts).

---

## Monitoring Dashboard

`dashboard.html` is a self-contained HTML file that connects to the GitHub API to show:

- System status and last run health
- Full workflow run history with duration and trigger
- Agent activity feed
- Report file browser with inline viewer
- Next scheduled run estimate

**Usage:** Open in browser. Enter `owner/repository` in the header. For private repositories, add a GitHub Personal Access Token (PAT) in Config — it is stored in memory only and never persisted.

**GitHub Pages:** Commit `dashboard.html` to the repository root and enable Pages. Access the dashboard at `https://<owner>.github.io/<repo>/dashboard.html?repo=<owner>/<repo>`.

---

## Report Output

Each scan saves a structured text file to `reports/` following the naming convention:

```
reports/whale_scan_YYYYMMDD_HHMMSS.txt
reports/daily_scan_YYYYMMDD_HHMMSS.md
```

Reports are committed to `main` automatically by `github-actions[bot]`. The `reports/` directory is browsable in the repository and readable in the monitoring dashboard.

---

## Agent Loop

The agent follows a ReAct protocol with a hard 15-iteration limit:

```
Thought  →  parse task, identify required tool
Action   →  emit tool_call JSON block
Observe  →  receive tool output, update context
Repeat   →  until task complete or limit reached
Final Answer: <result>
```

If no tool call and no Final Answer is emitted after 5 iterations, the agent aborts with a diagnostic message. The loop will not retry a failed tool call with identical arguments.

---

## File Reference

```
.
├── .github/
│   └── workflows/
│       ├── agent.yml                 — On-demand agent workflow
│       └── whale_tracking.yml        — Scheduled scan workflow
├── agent/
│   ├── agent.py                      — Main ReAct loop
│   ├── tools.py                      — Tool implementations
│   └── birdeye_tracker.py            — Birdeye API + signal logic
├── reports/                          — Generated scan output (auto-committed)
├── dashboard.html                    — Operational monitoring UI
├── example_whale_tracking.py         — Standalone local test runner
├── requirements.txt                  — Python dependencies
├── AGENTS.md                         — Agent behavior specification
├── BIRDEYE_USAGE.md                  — Birdeye workflow reference
└── README.md                         — This file
```

---

## Troubleshooting

**Workflow fails with permission error**
Enable read and write permissions: `Settings → Actions → General → Workflow permissions`.

**NIM_API_KEY not found**
Verify the secret is named exactly `NIM_API_KEY` in repository secrets.

**Birdeye tools return empty results**
Confirm `BIRDEYE_API_KEY` is set. Without a key, public endpoints are subject to aggressive rate limiting. Test the key locally before committing.

**Reports contain placeholder text instead of real data**
This was caused by a logic inversion in `agent.py` where the Final Answer check ran before tool calls were dispatched. Fixed in the current version — the tool execution block now runs first on every iteration.

**Workflow does not trigger on issue comments**
Check `Settings → Actions → General → Allow all actions and reusable workflows`.

---

## Limitations

- Birdeye public API coverage is limited without an authenticated key.
- Signal confidence is heuristic-based. No backtesting framework is included.
- The agent runs on GitHub-hosted runners with a 6-hour job timeout. Long-running daily scans should complete well within this limit.
- `daily_scan()` calls multiple Birdeye endpoints in sequence. If rate limits are hit, partial data may be returned without error.

---

## Security

- API keys are stored as encrypted GitHub Secrets and injected at runtime. They are never written to logs, files, or committed to the repository.
- All issue and PR comment content is treated as untrusted input.
- The agent will not execute destructive git operations (force push, branch deletion) without explicit instruction.
- The dashboard connects to the GitHub public API only. No data is sent to any third party.

---

## License

MIT. Use at your own risk. This system does not constitute financial advice.
