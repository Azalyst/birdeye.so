"""
Tool implementations for the NIM Qwen Agent.
Includes multi-chain Birdeye whale tracking.
"""

import subprocess
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from birdeye_tracker import track_whale, find_pumps, analyze_token, daily_scan, SUPPORTED_CHAINS
    BIRDEYE_AVAILABLE = True
except ImportError:
    BIRDEYE_AVAILABLE = False

TOOLS = ["bash", "read_file", "write_file", "list_dir", "search"]
if BIRDEYE_AVAILABLE:
    TOOLS.extend(["track_whale", "find_pumps", "analyze_token", "daily_scan"])

MAX_OUTPUT = 8000


def _truncate(text: str) -> str:
    if len(text) > MAX_OUTPUT:
        half = MAX_OUTPUT // 2
        return text[:half] + f"\n... [truncated {len(text) - MAX_OUTPUT} chars] ...\n" + text[-half:]
    return text


def bash(cmd: str) -> str:
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, timeout=120,
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
        capture_output=True, text=True, timeout=30,
    )
    out = result.stdout + result.stderr
    return _truncate(out) if out.strip() else f"No matches for '{pattern}' in {path}"


def execute_tool(tool_name: str, args: dict) -> str:
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

    elif tool_name == "track_whale" and BIRDEYE_AVAILABLE:
        return track_whale(
            wallet_address=args.get("wallet_address", ""),
            chain=args.get("chain", "solana"),
            api_key=args.get("api_key", os.environ.get("BIRDEYE_API_KEY")),
        )

    elif tool_name == "find_pumps" and BIRDEYE_AVAILABLE:
        return find_pumps(
            chain=args.get("chain", "solana"),
            api_key=args.get("api_key", os.environ.get("BIRDEYE_API_KEY")),
        )

    elif tool_name == "analyze_token" and BIRDEYE_AVAILABLE:
        return analyze_token(
            token_address=args.get("token_address", ""),
            chain=args.get("chain", "solana"),
            api_key=args.get("api_key", os.environ.get("BIRDEYE_API_KEY")),
        )

    elif tool_name == "daily_scan" and BIRDEYE_AVAILABLE:
        # chains arg is optional — omit for all chains, or pass list e.g. ["solana","ethereum"]
        chains = args.get("chains", None)
        return daily_scan(
            chains=chains,
            api_key=args.get("api_key", os.environ.get("BIRDEYE_API_KEY")),
        )

    else:
        supported = list(SUPPORTED_CHAINS.keys()) if BIRDEYE_AVAILABLE else []
        return (
            f"Unknown tool: {tool_name}. Available: {TOOLS}\n"
            f"Supported chains: {', '.join(supported)}"
        )
