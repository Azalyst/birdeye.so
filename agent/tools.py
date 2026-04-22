"""
Tool implementations for the NIM Qwen Agent.
Includes Birdeye whale tracking capabilities.
"""

import subprocess
import os
import sys

# Add current directory to path for birdeye_tracker import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from birdeye_tracker import track_whale, find_pumps, analyze_token, daily_scan, get_profitable_traders, get_wallet_pnl, get_top_traders, check_token_security, get_new_listings, get_token_creation_info, get_holder_list, get_wallet_pnl_details, get_trader_txs, get_ohlcv, get_wallet_token_list, get_wallet_tx_list
    BIRDEYE_AVAILABLE = True
except ImportError:
    BIRDEYE_AVAILABLE = False

TOOLS = ["bash", "read_file", "write_file", "list_dir", "search"]

# Add Birdeye tools if module is available
if BIRDEYE_AVAILABLE:
    TOOLS.extend(["track_whale", "find_pumps", "analyze_token", "daily_scan", "get_profitable_traders", "get_wallet_pnl", "get_top_traders", "check_token_security", "get_new_listings", "get_token_creation_info", "get_holder_list", "get_wallet_pnl_details", "get_trader_txs", "get_ohlcv", "get_wallet_token_list", "get_wallet_tx_list"])

MAX_OUTPUT = 8000  # chars


def _truncate(text: str) -> str:
    if len(text) > MAX_OUTPUT:
        half = MAX_OUTPUT // 2
        return text[:half] + f"\n... [truncated {len(text) - MAX_OUTPUT} chars] ...\n" + text[-half:]
    return text


def bash(cmd: str) -> str:
    result = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        timeout=120,
        cwd=os.environ.get("GITHUB_WORKSPACE", "."),
    )
    out = result.stdout + result.stderr
    return _truncate(out) if out.strip() else "(no output)"


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
            # Skip hidden dirs and common noise
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("node_modules", "__pycache__", ".git")]
            level = root.replace(path, "").count(os.sep)
            indent = "  " * level
            entries.append(f"{indent}{os.path.basename(root)}/")
            subindent = "  " * (level + 1)
            for f in files:
                entries.append(f"{subindent}{f}")
            if level >= 3:
                dirs.clear()  # Don't go deeper than 3 levels
        return "\n".join(entries) or "(empty)"
    except Exception as e:
        return f"Error listing {path}: {e}"


def search(pattern: str, path: str = ".") -> str:
    result = subprocess.run(
        ["grep", "-rn", "--include=*", pattern, path],
        capture_output=True,
        text=True,
        timeout=30,
    )
    out = result.stdout + result.stderr
    return _truncate(out) if out.strip() else f"No matches for '{pattern}' in {path}"


def execute_tool(tool_name: str, args: dict) -> str:
    """Execute a tool by name with given arguments"""
    
    # Original tools
    if tool_name == "bash":
        return bash(args.get("cmd", ""))
    elif tool_name == "read_file":
        return read_file(args.get("path", ""))
    elif tool_name == "write_file":
        return write_file(args.get("path", ""), args.get("content", ""))
    elif tool_name == "list_dir":
        return list_dir(args.get("path", "."))
    elif tool_name == "search":
        return search(args.get("pattern", ""), args.get("path", "."))
    
    # Birdeye tracking tools
    elif tool_name == "track_whale" and BIRDEYE_AVAILABLE:
        wallet = args.get("wallet_address", "")
        api_key = args.get("api_key", os.environ.get("BIRDEYE_API_KEY"))
        return track_whale(wallet, api_key)
    
    elif tool_name == "find_pumps" and BIRDEYE_AVAILABLE:
        api_key = args.get("api_key", os.environ.get("BIRDEYE_API_KEY"))
        return find_pumps(api_key)
    
    elif tool_name == "analyze_token" and BIRDEYE_AVAILABLE:
        token = args.get("token_address", "")
        api_key = args.get("api_key", os.environ.get("BIRDEYE_API_KEY"))
        return analyze_token(token, api_key)
    
    elif tool_name == "daily_scan" and BIRDEYE_AVAILABLE:
        api_key = args.get("api_key", os.environ.get("BIRDEYE_API_KEY"))
        return daily_scan(api_key)
    
    # New Birdeye tools
    elif tool_name == "get_profitable_traders" and BIRDEYE_AVAILABLE:
        chain = args.get("chain", "solana")
        time_frame = args.get("time_frame", "7D")
        api_key = args.get("api_key", os.environ.get("BIRDEYE_API_KEY"))
        return get_profitable_traders(chain=chain, time_frame=time_frame, api_key=api_key)
    
    elif tool_name == "get_wallet_pnl" and BIRDEYE_AVAILABLE:
        wallet = args.get("wallet_address", "")
        chain = args.get("chain", "solana")
        api_key = args.get("api_key", os.environ.get("BIRDEYE_API_KEY"))
        return get_wallet_pnl(wallet_address=wallet, chain=chain, api_key=api_key)
    
    elif tool_name == "get_top_traders" and BIRDEYE_AVAILABLE:
        token = args.get("token_address", "")
        chain = args.get("chain", "solana")
        time_frame = args.get("time_frame", "24h")
        api_key = args.get("api_key", os.environ.get("BIRDEYE_API_KEY"))
        return get_top_traders(token_address=token, chain=chain, time_frame=time_frame, api_key=api_key)
    
    elif tool_name == "check_token_security" and BIRDEYE_AVAILABLE:
        token = args.get("token_address", "")
        chain = args.get("chain", "solana")
        api_key = args.get("api_key", os.environ.get("BIRDEYE_API_KEY"))
        return check_token_security(token_address=token, chain=chain, api_key=api_key)
    
    # New Birdeye tools for complete feature coverage
    elif tool_name == "get_new_listings" and BIRDEYE_AVAILABLE:
        chain = args.get("chain", "solana")
        limit = args.get("limit", 50)
        api_key = args.get("api_key", os.environ.get("BIRDEYE_API_KEY"))
        return get_new_listings(chain=chain, limit=limit, api_key=api_key)
    
    elif tool_name == "get_token_creation_info" and BIRDEYE_AVAILABLE:
        token = args.get("token_address", "")
        chain = args.get("chain", "solana")
        api_key = args.get("api_key", os.environ.get("BIRDEYE_API_KEY"))
        return get_token_creation_info(token_address=token, chain=chain, api_key=api_key)
    
    elif tool_name == "get_holder_list" and BIRDEYE_AVAILABLE:
        token = args.get("token_address", "")
        chain = args.get("chain", "solana")
        limit = args.get("limit", 100)
        api_key = args.get("api_key", os.environ.get("BIRDEYE_API_KEY"))
        return get_holder_list(token_address=token, chain=chain, limit=limit, api_key=api_key)
    
    elif tool_name == "get_wallet_pnl_details" and BIRDEYE_AVAILABLE:
        wallet = args.get("wallet_address", "")
        chain = args.get("chain", "solana")
        limit = args.get("limit", 100)
        api_key = args.get("api_key", os.environ.get("BIRDEYE_API_KEY"))
        return get_wallet_pnl_details(wallet_address=wallet, chain=chain, limit=limit, api_key=api_key)
    
    elif tool_name == "get_trader_txs" and BIRDEYE_AVAILABLE:
        wallet = args.get("wallet_address", "")
        chain = args.get("chain", "solana")
        start_time = args.get("start_time")
        end_time = args.get("end_time")
        limit = args.get("limit", 50)
        api_key = args.get("api_key", os.environ.get("BIRDEYE_API_KEY"))
        return get_trader_txs(wallet_address=wallet, chain=chain, start_time=start_time, end_time=end_time, limit=limit, api_key=api_key)
    
    elif tool_name == "get_ohlcv" and BIRDEYE_AVAILABLE:
        token = args.get("token_address", "")
        chain = args.get("chain", "solana")
        timeframe = args.get("timeframe", "1h")
        api_key = args.get("api_key", os.environ.get("BIRDEYE_API_KEY"))
        return get_ohlcv(token_address=token, chain=chain, timeframe=timeframe, api_key=api_key)
    
    elif tool_name == "get_wallet_token_list" and BIRDEYE_AVAILABLE:
        wallet = args.get("wallet_address", "")
        chain = args.get("chain", "solana")
        api_key = args.get("api_key", os.environ.get("BIRDEYE_API_KEY"))
        return get_wallet_token_list(wallet_address=wallet, chain=chain, api_key=api_key)
    
    elif tool_name == "get_wallet_tx_list" and BIRDEYE_AVAILABLE:
        wallet = args.get("wallet_address", "")
        chain = args.get("chain", "solana")
        page = args.get("page", 1)
        page_size = args.get("page_size", 20)
        api_key = args.get("api_key", os.environ.get("BIRDEYE_API_KEY"))
        return get_wallet_tx_list(wallet_address=wallet, chain=chain, page=page, page_size=page_size, api_key=api_key)
    
    else:
        return f"Unknown tool: {tool_name}. Available: {TOOLS}"
