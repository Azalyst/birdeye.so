"""
Birdeye Whale Tracking Module — Multi-Chain
Supports: Solana, Ethereum, Base, Arbitrum, BNB, Avalanche, Polygon, Optimism, zkSync
"""

import requests
import json
import time
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict


SUPPORTED_CHAINS = {
    "solana":    "solana",
    "ethereum":  "ethereum",
    "base":      "base",
    "arbitrum":  "arbitrum",
    "bnb":       "bsc",
    "avalanche": "avalanche",
    "polygon":   "polygon",
    "optimism":  "optimism",
    "zksync":    "zksync",
}

DEFAULT_CHAIN = "solana"


@dataclass
class WhaleWallet:
    address: str
    chain: str
    total_holdings: float
    recent_activity: List[Dict]
    most_held_tokens: List[Dict]
    last_updated: str

    def to_dict(self):
        return asdict(self)


@dataclass
class TokenSignal:
    token_address: str
    token_name: str
    chain: str
    signal_type: str    # 'pump' or 'dump'
    confidence: float   # 0-1
    indicators: List[str]
    timestamp: str

    def to_dict(self):
        return asdict(self)


class BirdeyeAPI:
    BASE_URL = "https://public-api.birdeye.so"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.headers = {
            "X-API-KEY": api_key if api_key else "",
            "Accept": "application/json",
        }

    def _chain_header(self, chain: str) -> Dict:
        """Birdeye requires x-chain header for chain selection."""
        resolved = SUPPORTED_CHAINS.get(chain.lower(), chain.lower())
        return {**self.headers, "x-chain": resolved}

    def get_trending_tokens(self, chain: str = DEFAULT_CHAIN, time_frame: str = "24h") -> List[Dict]:
        endpoint = f"{self.BASE_URL}/defi/trending_tokens/{SUPPORTED_CHAINS.get(chain.lower(), chain)}"
        params = {"time_frame": time_frame}
        try:
            r = requests.get(endpoint, headers=self._chain_header(chain), params=params, timeout=10)
            if r.status_code == 200:
                return r.json().get("data", [])
            return []
        except Exception as e:
            return [{"error": str(e)}]

    def get_wallet_portfolio(self, wallet_address: str, chain: str = DEFAULT_CHAIN) -> Dict:
        endpoint = f"{self.BASE_URL}/v1/wallet/token_list"
        params = {"wallet": wallet_address}
        try:
            r = requests.get(endpoint, headers=self._chain_header(chain), params=params, timeout=10)
            if r.status_code == 200:
                return r.json().get("data", {})
            return {}
        except Exception as e:
            return {"error": str(e)}

    def get_token_overview(self, token_address: str, chain: str = DEFAULT_CHAIN) -> Dict:
        endpoint = f"{self.BASE_URL}/defi/token_overview"
        params = {"address": token_address}
        try:
            r = requests.get(endpoint, headers=self._chain_header(chain), params=params, timeout=10)
            if r.status_code == 200:
                return r.json().get("data", {})
            return {}
        except Exception as e:
            return {"error": str(e)}

    def get_token_trades(self, token_address: str, chain: str = DEFAULT_CHAIN, limit: int = 100) -> List[Dict]:
        endpoint = f"{self.BASE_URL}/defi/txs/token"
        params = {"address": token_address, "limit": limit, "offset": 0}
        try:
            r = requests.get(endpoint, headers=self._chain_header(chain), params=params, timeout=10)
            if r.status_code == 200:
                return r.json().get("data", {}).get("items", [])
            return []
        except Exception as e:
            return [{"error": str(e)}]

    def get_token_security(self, token_address: str, chain: str = DEFAULT_CHAIN) -> Dict:
        endpoint = f"{self.BASE_URL}/defi/token_security"
        params = {"address": token_address}
        try:
            r = requests.get(endpoint, headers=self._chain_header(chain), params=params, timeout=10)
            if r.status_code == 200:
                return r.json().get("data", {})
            return {}
        except Exception as e:
            return {"error": str(e)}


class WhaleTracker:
    def __init__(self, api_key: Optional[str] = None, default_chain: str = DEFAULT_CHAIN):
        self.api = BirdeyeAPI(api_key)
        self.default_chain = default_chain.lower()
        self.tracked_wallets: Dict[str, WhaleWallet] = {}
        self.watchlist: List[Dict] = []   # [{address, chain}]

    def _resolve_chain(self, chain: Optional[str]) -> str:
        c = (chain or self.default_chain).lower()
        if c not in SUPPORTED_CHAINS:
            raise ValueError(f"Unsupported chain '{c}'. Supported: {', '.join(SUPPORTED_CHAINS)}")
        return c

    # ── Watchlist ──

    def add_to_watchlist(self, wallet_address: str, chain: Optional[str] = None) -> str:
        chain = self._resolve_chain(chain)
        entry = {"address": wallet_address, "chain": chain}
        if entry not in self.watchlist:
            self.watchlist.append(entry)
            return f"Added {wallet_address} ({chain}) to watchlist. Total: {len(self.watchlist)}"
        return "Wallet already in watchlist."

    # ── Wallet Analysis ──

    def analyze_wallet(self, wallet_address: str, chain: Optional[str] = None) -> WhaleWallet:
        chain = self._resolve_chain(chain)
        portfolio = self.api.get_wallet_portfolio(wallet_address, chain)
        tokens = portfolio.get("tokens", [])
        total_value = sum(float(t.get("value_usd", 0)) for t in tokens)
        most_held = sorted(tokens, key=lambda x: float(x.get("value_usd", 0)), reverse=True)[:10]

        wallet = WhaleWallet(
            address=wallet_address,
            chain=chain,
            total_holdings=total_value,
            recent_activity=[],
            most_held_tokens=most_held,
            last_updated=datetime.now().isoformat(),
        )
        self.tracked_wallets[f"{chain}:{wallet_address}"] = wallet
        return wallet

    # ── Whale Trade Discovery ──

    def find_whale_trades(self, min_value_usd: float = 10000, chain: Optional[str] = None) -> List[Dict]:
        chain = self._resolve_chain(chain)
        trending = self.api.get_trending_tokens(chain)
        whale_trades = []

        for token in trending[:10]:
            token_address = token.get("address", "")
            if not token_address:
                continue
            trades = self.api.get_token_trades(token_address, chain, limit=50)
            for trade in trades:
                value_usd = float(trade.get("value_usd", 0))
                if value_usd >= min_value_usd:
                    whale_trades.append({
                        "chain": chain,
                        "token": token.get("symbol", "Unknown"),
                        "token_address": token_address,
                        "wallet": trade.get("owner", ""),
                        "type": trade.get("type", ""),
                        "value_usd": value_usd,
                        "timestamp": trade.get("block_unix_time", 0),
                    })

        return sorted(whale_trades, key=lambda x: x["value_usd"], reverse=True)

    # ── Hidden Gems ──

    def find_hidden_gems(self,
                         min_lp_size: float = 2000,
                         min_volume_1h: float = 10000,
                         max_age_hours: int = 24,
                         chain: Optional[str] = None) -> List[Dict]:
        chain = self._resolve_chain(chain)
        trending = self.api.get_trending_tokens(chain, time_frame="1h")
        gems = []

        for token in trending:
            token_address = token.get("address", "")
            if not token_address:
                continue

            overview = self.api.get_token_overview(token_address, chain)
            security = self.api.get_token_security(token_address, chain)

            liquidity = float(overview.get("liquidity", 0))
            volume_1h = float(overview.get("v1h", 0))
            created_at = overview.get("created_at", 0)
            age_hours = (time.time() - created_at) / 3600 if created_at else 999
            is_mintable = security.get("is_mintable", True)
            top_holders = security.get("top_10_holder_percent", 100)

            if (liquidity >= min_lp_size and
                    volume_1h >= min_volume_1h and
                    age_hours <= max_age_hours and
                    not is_mintable and
                    top_holders < 50):
                gems.append({
                    "chain": chain,
                    "token": token.get("symbol", "Unknown"),
                    "address": token_address,
                    "liquidity_usd": liquidity,
                    "volume_1h_usd": volume_1h,
                    "age_hours": round(age_hours, 2),
                    "holder_count": overview.get("holder", 0),
                    "price": overview.get("price", 0),
                    "score": self._calculate_gem_score(overview, security),
                })

        return sorted(gems, key=lambda x: x["score"], reverse=True)

    def _calculate_gem_score(self, overview: Dict, security: Dict) -> float:
        score = 0.0
        volume_1h = float(overview.get("v1h", 0))
        volume_24h = float(overview.get("v24h", 1))
        if volume_24h > 0:
            score += min((volume_1h / (volume_24h / 24)) * 10, 30)
        score += min(float(overview.get("holder_change_24h", 0)) / 50, 30)
        score += min(float(overview.get("liquidity", 0)) / 1000, 20)
        if not security.get("is_mintable"):
            score += 10
        if security.get("top_10_holder_percent", 100) < 30:
            score += 10
        return min(score, 100)

    # ── Signal Analysis ──

    def analyze_pump_dump_signals(self, token_address: str, chain: Optional[str] = None) -> TokenSignal:
        chain = self._resolve_chain(chain)
        overview = self.api.get_token_overview(token_address, chain)
        trades = self.api.get_token_trades(token_address, chain, limit=100)
        security = self.api.get_token_security(token_address, chain)

        red_flags, green_flags = [], []

        large_sells = [t for t in trades if t.get("type") == "sell" and float(t.get("value_usd", 0)) > 5000]
        large_buys  = [t for t in trades if t.get("type") == "buy"  and float(t.get("value_usd", 0)) > 5000]

        if len(large_sells) > len(large_buys) * 2:
            red_flags.append("Large wallet outflows detected")

        liquidity_change = float(overview.get("liquidity_change_24h", 0))
        if liquidity_change < -20:
            red_flags.append("LP pulled significantly")

        holder_change = float(overview.get("holder_change_24h", 0))
        if holder_change < -100:
            red_flags.append("Holder count dropping")
        elif holder_change > 500:
            green_flags.append("New holders spike")

        volume_1h  = float(overview.get("v1h", 0))
        volume_24h = float(overview.get("v24h", 1))
        if volume_24h > 0 and (volume_1h / (volume_24h / 24)) > 10:
            green_flags.append("Volume 10x in 1H")

        smart_buys = sum(1 for t in large_buys if len(t.get("owner", "")) > 30)
        if smart_buys > 3:
            green_flags.append("Smart wallets accumulating")

        dev_address = security.get("owner_address", "")
        if dev_address and any(t.get("owner") == dev_address and t.get("type") == "sell" for t in trades):
            red_flags.append("Dev wallet selling")

        if len(red_flags) > len(green_flags):
            signal_type, confidence, indicators = "dump", min(len(red_flags) / 5, 1.0), red_flags
        else:
            signal_type, confidence, indicators = "pump", min(len(green_flags) / 5, 1.0), green_flags

        return TokenSignal(
            token_address=token_address,
            token_name=overview.get("symbol", "Unknown"),
            chain=chain,
            signal_type=signal_type,
            confidence=confidence,
            indicators=indicators,
            timestamp=datetime.now().isoformat(),
        )

    # ── Daily Scan ──

    def run_daily_scan(self, chains: Optional[List[str]] = None) -> Dict:
        """
        Run full scan across one or more chains.
        Default: all supported chains.
        Pass chains=['solana','ethereum'] to limit scope.
        """
        target_chains = [self._resolve_chain(c) for c in (chains or list(SUPPORTED_CHAINS.keys()))]

        results = {
            "timestamp": datetime.now().isoformat(),
            "chains_scanned": target_chains,
            "trending_analysis": [],
            "whale_trades": [],
            "hidden_gems": [],
            "watchlist_updates": [],
        }

        for chain in target_chains:
            trending = self.api.get_trending_tokens(chain, time_frame="24h")
            for token in trending[:20]:
                token_address = token.get("address", "")
                if not token_address:
                    continue
                signal = self.analyze_pump_dump_signals(token_address, chain)
                results["trending_analysis"].append({
                    "chain": chain,
                    "token": token.get("symbol"),
                    "address": token_address,
                    "signal": signal.to_dict(),
                })

            results["whale_trades"].extend(self.find_whale_trades(min_value_usd=10000, chain=chain))
            results["hidden_gems"].extend(self.find_hidden_gems(chain=chain))

        # Sort cross-chain results by value
        results["whale_trades"].sort(key=lambda x: x["value_usd"], reverse=True)
        results["hidden_gems"].sort(key=lambda x: x["score"], reverse=True)
        results["whale_trades"]  = results["whale_trades"][:10]
        results["hidden_gems"]   = results["hidden_gems"][:10]

        for entry in self.watchlist:
            wallet_data = self.analyze_wallet(entry["address"], entry["chain"])
            results["watchlist_updates"].append({
                "chain": entry["chain"],
                "wallet": entry["address"],
                "total_holdings": wallet_data.total_holdings,
                "top_tokens": wallet_data.most_held_tokens[:5],
            })

        return results

    def format_report(self, scan_results: Dict) -> str:
        chains = ", ".join(c.upper() for c in scan_results.get("chains_scanned", []))
        report = [
            "=" * 70,
            "AZALYST WHALE TRACKING REPORT",
            f"Generated : {scan_results['timestamp']}",
            f"Chains    : {chains}",
            "=" * 70,
            "",
        ]

        report.append("TRENDING TOKEN SIGNALS")
        report.append("-" * 70)
        for item in scan_results["trending_analysis"][:10]:
            s = item["signal"]
            report.append(
                f"[{item['chain'].upper():10}] {item['token'] or '?':12} "
                f"{s['signal_type'].upper():5} {s['confidence']:.0%}  "
                f"{', '.join(s['indicators'][:2])}"
            )
        report.append("")

        report.append("TOP WHALE TRADES")
        report.append("-" * 70)
        for t in scan_results["whale_trades"]:
            w = t["wallet"]
            short = f"{w[:6]}...{w[-4:]}" if len(w) > 12 else w
            report.append(
                f"[{t['chain'].upper():10}] ${t['value_usd']:>12,.0f}  "
                f"{t['type'].upper():5}  {t['token']:12}  {short}"
            )
        report.append("")

        report.append("HIDDEN GEMS")
        report.append("-" * 70)
        for g in scan_results["hidden_gems"]:
            report.append(
                f"[{g['chain'].upper():10}] {g['token']:12}  Score {g['score']:5.1f}/100  "
                f"Age {g['age_hours']:.1f}h  Vol1H ${g['volume_1h_usd']:,.0f}  "
                f"LP ${g['liquidity_usd']:,.0f}"
            )

        return "\n".join(report)


# ── Agent-facing utility functions ──

def track_whale(wallet_address: str, chain: str = DEFAULT_CHAIN, api_key: Optional[str] = None) -> str:
    tracker = WhaleTracker(api_key, default_chain=chain)
    result = tracker.add_to_watchlist(wallet_address, chain)
    wallet_data = tracker.analyze_wallet(wallet_address, chain)
    return f"{result}\n\nWallet Analysis ({chain}):\n" + json.dumps(wallet_data.to_dict(), indent=2)


def find_pumps(chain: str = DEFAULT_CHAIN, api_key: Optional[str] = None) -> str:
    tracker = WhaleTracker(api_key, default_chain=chain)
    gems = tracker.find_hidden_gems(chain=chain)
    if not gems:
        return f"No hidden gems found on {chain} matching current criteria."
    lines = [f"POTENTIAL PUMP TOKENS — {chain.upper()}\n"]
    for i, g in enumerate(gems[:10], 1):
        lines.append(f"{i:2}. {g['token']:12}  Score {g['score']:5.1f}/100  "
                     f"${g['volume_1h_usd']:,.0f} vol  {g['age_hours']:.1f}h old")
    return "\n".join(lines)


def analyze_token(token_address: str, chain: str = DEFAULT_CHAIN, api_key: Optional[str] = None) -> str:
    tracker = WhaleTracker(api_key, default_chain=chain)
    signal = tracker.analyze_pump_dump_signals(token_address, chain)
    lines = [
        f"TOKEN SIGNAL — {chain.upper()}",
        f"Token      : {signal.token_name}",
        f"Signal     : {signal.signal_type.upper()}",
        f"Confidence : {signal.confidence:.0%}",
        "",
        "Indicators :",
    ]
    for ind in signal.indicators:
        lines.append(f"  - {ind}")
    return "\n".join(lines)


def daily_scan(chains: Optional[List[str]] = None, api_key: Optional[str] = None) -> str:
    """
    Run daily scan. Pass chains list to limit scope.
    Default scans all supported chains.
    Examples:
      daily_scan()                                  # all chains
      daily_scan(chains=['solana'])                 # Solana only
      daily_scan(chains=['ethereum','base'])        # ETH + Base
    """
    tracker = WhaleTracker(api_key)
    results = tracker.run_daily_scan(chains=chains)
    return tracker.format_report(results)
