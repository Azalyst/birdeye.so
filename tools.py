"""
Tool dispatcher for the NIM Qwen Agent.
Full Azalyst Alpha Scanner tool set with multi-chain support.
"""

import subprocess
import os
import sys
import shlex

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from azalyst_tracker import (
        track_whale, find_pumps, analyze_token, daily_scan,
        get_profitable_traders, get_wallet_pnl, get_top_traders,
        check_token_security, get_new_listings, get_token_creation_info,
        get_holder_list, get_wallet_pnl_details, get_trader_txs,
        get_ohlcv, get_wallet_token_list, get_wallet_tx_list,
        SUPPORTED_CHAINS,
    )
    AZALYST_AVAILABLE = True
except ImportError:
    AZALYST_AVAILABLE = False
    SUPPORTED_CHAINS = {}

TOOLS = ["bash", "read_file", "write_file", "list_dir", "search"]
if AZALYST_AVAILABLE:
    TOOLS.extend([
        "track_whale", "find_pumps", "analyze_token", "daily_scan",
        "get_profitable_traders", "get_wallet_pnl", "get_top_traders",
        "check_token_security", "get_new_listings", "get_token_creation_info",
        "get_holder_list", "get_wallet_pnl_details", "get_trader_txs",
        "get_ohlcv", "get_wallet_token_list", "get_wallet_tx_list",
    ])

MAX_OUTPUT = 8000


def _truncate(text: str) -> str:
    if len(text) > MAX_OUTPUT:
        half = MAX_OUTPUT // 2
        return text[:half] + f"\n... [truncated {len(text) - MAX_OUTPUT} chars] ...\n" + text[-half:]
    return text


ALLOWED_BASH_PREFIXES = (
    "ls", "cat", "head", "tail", "wc", "grep", "find",
    "python", "pytest", "pip list", "git status", "git diff", "git log",
)
DENIED_PATTERNS = ("rm ", "rm\t", " rm", ";rm", "&&rm", "|rm",
                   "git push", "git reset --hard", "curl ", "wget ",
                   "chmod ", "chown ", "sudo ", "/dev/", ":(){", "dd if=")

def _is_allowed(cmd: str) -> bool:
    c = cmd.strip()
    if any(bad in c for bad in DENIED_PATTERNS):
        return False
    return any(c.startswith(prefix) for prefix in ALLOWED_BASH_PREFIXES)

def bash(cmd: str, timeout: int = 120) -> str:
    """Run a whitelisted shell command. NEVER pass shell=True."""
    if not isinstance(cmd, str) or not cmd.strip():
        return "ERROR: empty command"
    if not _is_allowed(cmd):
        return f"ERROR: command not allowed by safety policy: {cmd!r}"
    try:
        result = subprocess.run(
            shlex.split(cmd),
            shell=False,                # critical
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            cwd=os.environ.get("GITHUB_WORKSPACE", "."),
        )
        out = (result.stdout or "") + (result.stderr or "")
        return _truncate(out[:4000])               # hard truncate
    except subprocess.TimeoutExpired:
        return f"ERROR: timeout after {timeout}s"
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


def read_file(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return _truncate(f.read())
    except FileNotFoundError:
        return f"Error: file not found: {path}"
    except Exception as e:
        return f"Error reading {path}: {e}"


def write_file(path: str, content: str) -> str:
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Written {len(content)} chars to {path}"
    except Exception as e:
        return f"Error writing {path}: {e}"


def list_dir(path: str = ".") -> str:
    try:
        entries = []
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("node_modules", "__pycache__", ".git")]
            level = root.replace(path, "").count(os.sep)
            entries.append("  " * level + os.path.basename(root) + "/")
            for f in files:
                entries.append("  " * (level + 1) + f)
            if level >= 3:
                dirs.clear()
        return "\n".join(entries) or "(empty)"
    except Exception as e:
        return f"Error listing {path}: {e}"


def search(pattern: str, path: str = ".") -> str:
    result = subprocess.run(
        ["grep", "-rn", "--include=*", pattern, path],
        shell=False,
        capture_output=True, text=True, timeout=30,
    )
    out = result.stdout + result.stderr
    return _truncate(out) if out.strip() else f"No matches for '{pattern}' in {path}"


def _api_key(args: dict) -> str:
    return args.get("api_key", os.environ.get("HELIUS_API_KEY"))


def execute_tool(tool_name: str, args: dict) -> str:
    # ── Core tools ──────────────────────────────────────────────────────────
    if tool_name == "bash":
        return bash(args.get("cmd", ""))
    if tool_name == "read_file":
        return read_file(args.get("path", ""))
    if tool_name == "write_file":
        return write_file(args.get("path", ""), args.get("content", ""))
    if tool_name == "list_dir":
        return list_dir(args.get("path", "."))
    if tool_name == "search":
        return search(args.get("pattern", ""), args.get("path", "."))

    if not AZALYST_AVAILABLE:
        return f"Azalyst module not available. Tool '{tool_name}' cannot run."

    # ── Azalyst tools ────────────────────────────────────────────────────────
    key = _api_key(args)

    if tool_name == "track_whale":
        return track_whale(
            wallet_address=args.get("wallet_address", ""),
            chain=args.get("chain", "solana"),
            api_key=key,
        )

    if tool_name == "find_pumps":
        return find_pumps(
            chain=args.get("chain", "solana"),
            api_key=key,
        )

    if tool_name == "analyze_token":
        return analyze_token(
            token_address=args.get("token_address", ""),
            chain=args.get("chain", "solana"),
            api_key=key,
        )

    if tool_name == "daily_scan":
        return daily_scan(
            chains=args.get("chains"),   # None → all chains
            api_key=key,
        )

    if tool_name == "get_profitable_traders":
        return get_profitable_traders(
            chain=args.get("chain", "solana"),
            time_frame=args.get("time_frame", "7D"),
            api_key=key,
        )

    if tool_name == "get_wallet_pnl":
        return get_wallet_pnl(
            wallet_address=args.get("wallet_address", ""),
            chain=args.get("chain", "solana"),
            api_key=key,
        )

    if tool_name == "get_top_traders":
        return get_top_traders(
            token_address=args.get("token_address", ""),
            chain=args.get("chain", "solana"),
            time_frame=args.get("time_frame", "24h"),
            api_key=key,
        )

    if tool_name == "check_token_security":
        return check_token_security(
            token_address=args.get("token_address", ""),
            chain=args.get("chain", "solana"),
            api_key=key,
        )

    if tool_name == "get_new_listings":
        return get_new_listings(
            chain=args.get("chain", "solana"),
            limit=args.get("limit", 50),
            api_key=key,
        )

    if tool_name == "get_token_creation_info":
        return get_token_creation_info(
            token_address=args.get("token_address", ""),
            chain=args.get("chain", "solana"),
            api_key=key,
        )

    if tool_name == "get_holder_list":
        return get_holder_list(
            token_address=args.get("token_address", ""),
            chain=args.get("chain", "solana"),
            limit=args.get("limit", 100),
            api_key=key,
        )

    if tool_name == "get_wallet_pnl_details":
        return get_wallet_pnl_details(
            wallet_address=args.get("wallet_address", ""),
            chain=args.get("chain", "solana"),
            limit=args.get("limit", 100),
            api_key=key,
        )

    if tool_name == "get_trader_txs":
        return get_trader_txs(
            wallet_address=args.get("wallet_address", ""),
            chain=args.get("chain", "solana"),
            start_time=args.get("start_time"),
            end_time=args.get("end_time"),
            limit=args.get("limit", 50),
            api_key=key,
        )

    if tool_name == "get_ohlcv":
        return get_ohlcv(
            token_address=args.get("token_address", ""),
            chain=args.get("chain", "solana"),
            timeframe=args.get("timeframe", "1h"),
            api_key=key,
        )

    if tool_name == "get_wallet_token_list":
        return get_wallet_token_list(
            wallet_address=args.get("wallet_address", ""),
            chain=args.get("chain", "solana"),
            api_key=key,
        )

    if tool_name == "get_wallet_tx_list":
        return get_wallet_tx_list(
            wallet_address=args.get("wallet_address", ""),
            chain=args.get("chain", "solana"),
            page=args.get("page", 1),
            page_size=args.get("page_size", 20),
            api_key=key,
        )

    return (
        f"Unknown tool: '{tool_name}'.\n"
        f"Available tools: {TOOLS}\n"
        f"Supported chains: {', '.join(SUPPORTED_CHAINS.keys())}"
    )
