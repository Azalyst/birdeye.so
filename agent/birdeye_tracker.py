"""
Birdeye Whale Tracking Module
Implements the complete whale tracking workflow for Birdeye.so
"""

import requests
import json
import time
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict


@dataclass
class WhaleWallet:
    """Represents a whale wallet being tracked"""
    address: str
    total_holdings: float
    recent_activity: List[Dict]
    most_held_tokens: List[Dict]
    last_updated: str
    
    def to_dict(self):
        return asdict(self)


@dataclass
class TokenSignal:
    """Represents pump/dump signals for a token"""
    token_address: str
    token_name: str
    signal_type: str  # 'pump' or 'dump'
    confidence: float  # 0-1
    indicators: List[str]
    timestamp: str
    
    def to_dict(self):
        return asdict(self)


class BirdeyeAPI:
    """Wrapper for Birdeye API interactions"""
    
    BASE_URL = "https://public-api.birdeye.so"
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.headers = {
            "X-API-KEY": api_key if api_key else "",
            "Accept": "application/json"
        }
    
    def get_trending_tokens(self, chain: str = "solana", time_frame: str = "24h") -> List[Dict]:
        """Get trending tokens on Birdeye"""
        endpoint = f"{self.BASE_URL}/defi/trending_tokens/{chain}"
        params = {"time_frame": time_frame}
        
        try:
            response = requests.get(endpoint, headers=self.headers, params=params, timeout=10)
            if response.status_code == 200:
                return response.json().get("data", [])
            return []
        except Exception as e:
            return [{"error": str(e)}]
    
    def get_wallet_portfolio(self, wallet_address: str) -> Dict:
        """Get wallet holdings and portfolio breakdown"""
        endpoint = f"{self.BASE_URL}/v1/wallet/token_list"
        params = {"wallet": wallet_address}
        
        try:
            response = requests.get(endpoint, headers=self.headers, params=params, timeout=10)
            if response.status_code == 200:
                return response.json().get("data", {})
            return {}
        except Exception as e:
            return {"error": str(e)}
    
    def get_token_overview(self, token_address: str) -> Dict:
        """Get comprehensive token overview including metrics"""
        endpoint = f"{self.BASE_URL}/defi/token_overview"
        params = {"address": token_address}
        
        try:
            response = requests.get(endpoint, headers=self.headers, params=params, timeout=10)
            if response.status_code == 200:
                return response.json().get("data", {})
            return {}
        except Exception as e:
            return {"error": str(e)}
    
    def get_token_trades(self, token_address: str, limit: int = 100) -> List[Dict]:
        """Get recent trades for a token"""
        endpoint = f"{self.BASE_URL}/defi/txs/token"
        params = {
            "address": token_address,
            "limit": limit,
            "offset": 0
        }
        
        try:
            response = requests.get(endpoint, headers=self.headers, params=params, timeout=10)
            if response.status_code == 200:
                return response.json().get("data", {}).get("items", [])
            return []
        except Exception as e:
            return [{"error": str(e)}]
    
    def get_token_security(self, token_address: str) -> Dict:
        """Get token security analysis"""
        endpoint = f"{self.BASE_URL}/defi/token_security"
        params = {"address": token_address}
        
        try:
            response = requests.get(endpoint, headers=self.headers, params=params, timeout=10)
            if response.status_code == 200:
                return response.json().get("data", {})
            return {}
        except Exception as e:
            return {"error": str(e)}
    
    def get_profitable_traders(self, chain: str = "solana", time_frame: str = "7D", limit: int = 20) -> List[Dict]:
        """Get profitable traders leaderboard (gainers)"""
        endpoint = f"{self.BASE_URL}/trader/gainers-losers"
        params = {
            "type": "gainers",
            "sort_by": "PnL",
            "time_frame": time_frame,
            "limit": limit
        }
        
        # Add chain header
        headers = self.headers.copy()
        headers["x-chain"] = chain
        
        try:
            response = requests.get(endpoint, headers=headers, params=params, timeout=15)
            if response.status_code == 200:
                data = response.json().get("data", [])
                # Enrich with chain info
                for trader in data:
                    trader["chain"] = chain
                return data
            return []
        except Exception as e:
            return [{"error": str(e)}]
    
    def get_wallet_pnl(self, wallet_address: str, chain: str = "solana") -> Dict:
        """Get wallet PnL summary"""
        endpoint = f"{self.BASE_URL}/wallet/v2/pnl/summary"
        
        # Add chain header
        headers = self.headers.copy()
        headers["x-chain"] = chain
        headers["Content-Type"] = "application/json"
        
        body = {"wallet": wallet_address}
        
        try:
            response = requests.post(endpoint, headers=headers, json=body, timeout=15)
            if response.status_code == 200:
                return response.json().get("data", {})
            return {}
        except Exception as e:
            return {"error": str(e)}
    
    def get_top_traders(self, token_address: str, chain: str = "solana", time_frame: str = "24h", limit: int = 10) -> List[Dict]:
        """Get top traders for a specific token"""
        endpoint = f"{self.BASE_URL}/defi/v2/tokens/top_traders"
        params = {
            "address": token_address,
            "time_frame": time_frame,
            "sort_by": "volume",
            "limit": limit
        }
        
        # Add chain header
        headers = self.headers.copy()
        headers["x-chain"] = chain
        
        try:
            response = requests.get(endpoint, headers=headers, params=params, timeout=15)
            if response.status_code == 200:
                data = response.json().get("data", [])
                # Enrich with token and chain info
                for trader in data:
                    trader["token_address"] = token_address
                    trader["chain"] = chain
                return data
            return []
        except Exception as e:
            return [{"error": str(e)}]
    
    def get_new_listings(self, chain: str = "solana", limit: int = 50) -> List[Dict]:
        """Get newly listed tokens — catch before they pump"""
        endpoint = f"{self.BASE_URL}/defi/v2/tokens/new_listing"
        params = {"limit": limit}
        
        # Add chain header
        headers = self.headers.copy()
        headers["x-chain"] = chain
        
        try:
            response = requests.get(endpoint, headers=headers, params=params, timeout=15)
            if response.status_code == 200:
                data = response.json().get("data", [])
                for token in data:
                    token["chain"] = chain
                return data
            return []
        except Exception as e:
            return [{"error": str(e)}]
    
    def get_token_creation_info(self, token_address: str, chain: str = "solana") -> Dict:
        """Get token creation info: deployer wallet, creation time, initial supply"""
        endpoint = f"{self.BASE_URL}/defi/token_creation_info"
        params = {"address": token_address}
        
        # Add chain header
        headers = self.headers.copy()
        headers["x-chain"] = chain
        
        try:
            response = requests.get(endpoint, headers=headers, params=params, timeout=15)
            if response.status_code == 200:
                return response.json().get("data", {})
            return {}
        except Exception as e:
            return {"error": str(e)}
    
    def get_holder_list(self, token_address: str, chain: str = "solana", limit: int = 100) -> List[Dict]:
        """Get all wallets holding a token, sorted by balance"""
        endpoint = f"{self.BASE_URL}/defi/v3/token/holder"
        params = {"address": token_address, "limit": limit}
        
        # Add chain header
        headers = self.headers.copy()
        headers["x-chain"] = chain
        
        try:
            response = requests.get(endpoint, headers=headers, params=params, timeout=15)
            if response.status_code == 200:
                return response.json().get("data", {}).get("holders", [])
            return []
        except Exception as e:
            return [{"error": str(e)}]
    
    def get_wallet_pnl_details(self, wallet_address: str, chain: str = "solana", limit: int = 100) -> List[Dict]:
        """Get token-by-token PnL breakdown for a wallet (up to 100 tokens)"""
        endpoint = f"{self.BASE_URL}/wallet/v2/pnl/details"
        
        headers = self.headers.copy()
        headers["x-chain"] = chain
        headers["Content-Type"] = "application/json"
        
        body = {"wallet": wallet_address, "limit": limit}
        
        try:
            response = requests.post(endpoint, headers=headers, json=body, timeout=15)
            if response.status_code == 200:
                return response.json().get("data", [])
            return []
        except Exception as e:
            return [{"error": str(e)}]
    
    def get_trader_txs(self, wallet_address: str, chain: str = "solana", start_time: int = None, end_time: int = None, limit: int = 50) -> List[Dict]:
        """Get all trades by a wallet with time-bound filtering"""
        endpoint = f"{self.BASE_URL}/trader/txs/seek_by_time"
        params = {"wallet": wallet_address, "limit": limit}
        
        if start_time:
            params["start_time"] = start_time
        if end_time:
            params["end_time"] = end_time
        
        # Add chain header
        headers = self.headers.copy()
        headers["x-chain"] = chain
        
        try:
            response = requests.get(endpoint, headers=headers, params=params, timeout=15)
            if response.status_code == 200:
                return response.json().get("data", {}).get("items", [])
            return []
        except Exception as e:
            return [{"error": str(e)}]
    
    def get_pair_overview_single(self, pair_address: str, chain: str = "solana", timeframes: List[str] = None) -> Dict:
        """Get volume, wallets, trade history for one pair across timeframes"""
        endpoint = f"{self.BASE_URL}/defi/v3/pair/overview/single"
        params = {"pair_address": pair_address}
        
        if timeframes:
            params["timeframes"] = ",".join(timeframes)
        
        # Add chain header
        headers = self.headers.copy()
        headers["x-chain"] = chain
        
        try:
            response = requests.get(endpoint, headers=headers, params=params, timeout=15)
            if response.status_code == 200:
                return response.json().get("data", {})
            return {}
        except Exception as e:
            return {"error": str(e)}
    
    def get_pair_overview_multiple(self, pair_addresses: List[str], chain: str = "solana") -> List[Dict]:
        """Batch pair metrics — great for comparing pools"""
        endpoint = f"{self.BASE_URL}/defi/v3/pair/overview/multiple"
        
        headers = self.headers.copy()
        headers["x-chain"] = chain
        headers["Content-Type"] = "application/json"
        
        body = {"pair_addresses": pair_addresses}
        
        try:
            response = requests.post(endpoint, headers=headers, json=body, timeout=15)
            if response.status_code == 200:
                return response.json().get("data", [])
            return []
        except Exception as e:
            return [{"error": str(e)}]
    
    def get_ohlcv(self, token_address: str, chain: str = "solana", timeframe: str = "1h", from_time: int = None, to_time: int = None) -> List[Dict]:
        """Get OHLCV candles — 1s/15s/30s on Solana, standard intervals on all chains"""
        endpoint = f"{self.BASE_URL}/defi/v3/ohlcv"
        params = {"address": token_address, "timeframe": timeframe}
        
        if from_time:
            params["from_time"] = from_time
        if to_time:
            params["to_time"] = to_time
        
        # Add chain header
        headers = self.headers.copy()
        headers["x-chain"] = chain
        
        try:
            response = requests.get(endpoint, headers=headers, params=params, timeout=15)
            if response.status_code == 200:
                return response.json().get("data", [])
            return []
        except Exception as e:
            return [{"error": str(e)}]
    
    def get_token_trending(self, chain: str = "solana", sort_by: str = "volume", limit: int = 50) -> List[Dict]:
        """Get trending tokens — top movers of past 24h by price, volume, TVL"""
        endpoint = f"{self.BASE_URL}/defi/token_trending"
        params = {"sort_by": sort_by, "limit": limit}
        
        # Add chain header
        headers = self.headers.copy()
        headers["x-chain"] = chain
        
        try:
            response = requests.get(endpoint, headers=headers, params=params, timeout=15)
            if response.status_code == 200:
                data = response.json().get("data", [])
                for token in data:
                    token["chain"] = chain
                return data
            return []
        except Exception as e:
            return [{"error": str(e)}]
    
    def get_wallet_token_list(self, wallet_address: str, chain: str = "solana") -> List[Dict]:
        """Get current holdings with USD values across all supported chains"""
        endpoint = f"{self.BASE_URL}/v1/wallet/token_list"
        params = {"wallet": wallet_address}
        
        # Add chain header
        headers = self.headers.copy()
        headers["x-chain"] = chain
        
        try:
            response = requests.get(endpoint, headers=headers, params=params, timeout=15)
            if response.status_code == 200:
                return response.json().get("data", {}).get("tokens", [])
            return []
        except Exception as e:
            return [{"error": str(e)}]
    
    def get_wallet_tx_list(self, wallet_address: str, chain: str = "solana", page: int = 1, page_size: int = 20) -> List[Dict]:
        """Get every transaction a wallet has made on a given chain"""
        endpoint = f"{self.BASE_URL}/v1/wallet/tx_list"
        params = {"wallet": wallet_address, "page": page, "page_size": page_size}
        
        # Add chain header
        headers = self.headers.copy()
        headers["x-chain"] = chain
        
        try:
            response = requests.get(endpoint, headers=headers, params=params, timeout=15)
            if response.status_code == 200:
                return response.json().get("data", {}).get("txList", [])
            return []
        except Exception as e:
            return [{"error": str(e)}]


class WhaleTracker:
    """Main whale tracking logic implementing the Birdeye workflow"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api = BirdeyeAPI(api_key)
        self.tracked_wallets: Dict[str, WhaleWallet] = {}
        self.watchlist: List[str] = []
    
    # STEP 1: Find and Track Whale Wallets
    
    def find_whale_trades(self, min_value_usd: float = 10000) -> List[Dict]:
        """
        Find large whale trades from recent activity
        Step 1: Whale ka wallet pakad
        """
        trending = self.api.get_trending_tokens()
        whale_trades = []
        
        for token in trending[:10]:  # Check top 10 trending
            token_address = token.get("address", "")
            if not token_address:
                continue
                
            trades = self.api.get_token_trades(token_address, limit=50)
            
            for trade in trades:
                value_usd = float(trade.get("value_usd", 0))
                if value_usd >= min_value_usd:
                    whale_trades.append({
                        "token": token.get("symbol", "Unknown"),
                        "token_address": token_address,
                        "wallet": trade.get("owner", ""),
                        "type": trade.get("type", ""),
                        "value_usd": value_usd,
                        "timestamp": trade.get("block_unix_time", 0)
                    })
        
        return sorted(whale_trades, key=lambda x: x["value_usd"], reverse=True)
    
    def add_to_watchlist(self, wallet_address: str) -> str:
        """Add wallet to tracking watchlist"""
        if wallet_address not in self.watchlist:
            self.watchlist.append(wallet_address)
            return f"Added {wallet_address} to watchlist. Total: {len(self.watchlist)} wallets"
        return f"Wallet already in watchlist"
    
    # STEP 2: Deep Dive into Wallet
    
    def analyze_wallet(self, wallet_address: str) -> WhaleWallet:
        """
        Deep dive into wallet holdings and activity
        Step 2: Wallet deep dive
        """
        portfolio = self.api.get_wallet_portfolio(wallet_address)
        
        tokens = portfolio.get("tokens", [])
        total_value = sum(float(t.get("value_usd", 0)) for t in tokens)
        
        most_held = sorted(
            tokens,
            key=lambda x: float(x.get("value_usd", 0)),
            reverse=True
        )[:10]
        
        wallet = WhaleWallet(
            address=wallet_address,
            total_holdings=total_value,
            recent_activity=[],
            most_held_tokens=most_held,
            last_updated=datetime.now().isoformat()
        )
        
        self.tracked_wallets[wallet_address] = wallet
        return wallet
    
    # STEP 3: Pre-Pump Signals Detection
    
    def detect_accumulation_pattern(self, wallet_address: str, token_address: str) -> Dict:
        """
        Detect if wallet is accumulating a specific token
        Part of Step 3: Pump aane se pehle signals
        """
        trades = self.api.get_token_trades(token_address, limit=100)
        
        wallet_trades = [t for t in trades if t.get("owner") == wallet_address]
        
        buys = [t for t in wallet_trades if t.get("type") == "buy"]
        sells = [t for t in wallet_trades if t.get("type") == "sell"]
        
        buy_volume = sum(float(t.get("value_usd", 0)) for t in buys)
        sell_volume = sum(float(t.get("value_usd", 0)) for t in sells)
        
        return {
            "wallet": wallet_address,
            "token": token_address,
            "buy_count": len(buys),
            "sell_count": len(sells),
            "buy_volume_usd": buy_volume,
            "sell_volume_usd": sell_volume,
            "net_position": buy_volume - sell_volume,
            "is_accumulating": buy_volume > sell_volume * 2
        }
    
    def check_holder_growth(self, token_address: str) -> Dict:
        """
        Check if token is getting new holders (viral signal)
        Agar ek token mein 2,000 naye holders ek din mein aayein
        """
        token_data = self.api.get_token_overview(token_address)
        
        holder_count = token_data.get("holder", 0)
        holder_change_24h = token_data.get("holder_change_24h", 0)
        
        return {
            "token": token_address,
            "current_holders": holder_count,
            "holder_change_24h": holder_change_24h,
            "is_viral": holder_change_24h > 1000,
            "growth_rate": (holder_change_24h / holder_count * 100) if holder_count > 0 else 0
        }
    
    # STEP 4: Hidden Gem Filter
    
    def find_hidden_gems(self, 
                        min_lp_size: float = 2000,
                        min_volume_1h: float = 10000,
                        max_age_hours: int = 24) -> List[Dict]:
        """
        Filter tokens for early pump potential
        Step 4: Hidden gem filter (pump prediction)
        Filters: token age <24h, LP >2K, volume growth >10K in 1H
        Uses check_token_security to pre-filter risky tokens
        """
        trending = self.api.get_trending_tokens(time_frame="1h")
        gems = []
        
        for token in trending:
            token_address = token.get("address", "")
            if not token_address:
                continue
            
            overview = self.api.get_token_overview(token_address)
            security = self.api.get_token_security(token_address)
            
            # Check filters
            liquidity = float(overview.get("liquidity", 0))
            volume_1h = float(overview.get("v1h", 0))
            created_at = overview.get("created_at", 0)
            
            age_hours = (time.time() - created_at) / 3600 if created_at else 999
            
            # Security checks - pre-filter risky tokens
            is_mintable = security.get("is_mintable", True)
            top_holders = security.get("top_10_holder_percent", 100)
            freeze_authority = security.get("freeze_authority", False)
            
            # Skip high-risk tokens (rug risk score >= 50)
            rug_risk = 0
            if is_mintable:
                rug_risk += 30
            if freeze_authority:
                rug_risk += 25
            if top_holders > 50:
                rug_risk += 25
            if top_holders > 80:
                rug_risk += 20
            
            if rug_risk >= 50:
                continue  # Skip high-risk tokens
            
            if (liquidity >= min_lp_size and 
                volume_1h >= min_volume_1h and 
                age_hours <= max_age_hours and
                not is_mintable and
                top_holders < 50):  # Not too concentrated
                
                gems.append({
                    "token": token.get("symbol", "Unknown"),
                    "address": token_address,
                    "liquidity_usd": liquidity,
                    "volume_1h_usd": volume_1h,
                    "age_hours": round(age_hours, 2),
                    "holder_count": overview.get("holder", 0),
                    "price": overview.get("price", 0),
                    "score": self._calculate_gem_score(overview, security),
                    "rug_risk_score": rug_risk
                })
        
        return sorted(gems, key=lambda x: x["score"], reverse=True)
    
    def _calculate_gem_score(self, overview: Dict, security: Dict) -> float:
        """Calculate gem potential score (0-100)"""
        score = 0
        
        # Volume spike
        volume_1h = float(overview.get("v1h", 0))
        volume_24h = float(overview.get("v24h", 1))
        if volume_24h > 0:
            volume_spike = (volume_1h / (volume_24h / 24)) * 10
            score += min(volume_spike, 30)
        
        # Holder growth
        holder_change = float(overview.get("holder_change_24h", 0))
        score += min(holder_change / 50, 30)
        
        # Liquidity strength
        liquidity = float(overview.get("liquidity", 0))
        score += min(liquidity / 1000, 20)
        
        # Security bonus
        if not security.get("is_mintable"):
            score += 10
        if security.get("top_10_holder_percent", 100) < 30:
            score += 10
        
        return min(score, 100)
    
    # STEP 5: Signal Analysis (Pump vs Dump)
    
    def analyze_pump_dump_signals(self, token_address: str) -> TokenSignal:
        """
        Comprehensive pump/dump signal detection
        Combines all red/green flags from requirements
        """
        overview = self.api.get_token_overview(token_address)
        trades = self.api.get_token_trades(token_address, limit=100)
        security = self.api.get_token_security(token_address)
        
        red_flags = []
        green_flags = []
        
        # Analyze large wallet movements
        large_sells = [t for t in trades if t.get("type") == "sell" and float(t.get("value_usd", 0)) > 5000]
        large_buys = [t for t in trades if t.get("type") == "buy" and float(t.get("value_usd", 0)) > 5000]
        
        if len(large_sells) > len(large_buys) * 2:
            red_flags.append("Large wallet outflows detected")
        
        # LP analysis
        liquidity = float(overview.get("liquidity", 0))
        liquidity_change = float(overview.get("liquidity_change_24h", 0))
        
        if liquidity_change < -20:
            red_flags.append("LP pulled significantly")
        
        # Holder analysis
        holder_change = float(overview.get("holder_change_24h", 0))
        
        if holder_change < -100:
            red_flags.append("Holder count dropping")
        elif holder_change > 500:
            green_flags.append("New holders spike - viral signal")
        
        # Volume analysis
        volume_1h = float(overview.get("v1h", 0))
        volume_24h = float(overview.get("v24h", 1))
        
        if volume_24h > 0:
            volume_spike = volume_1h / (volume_24h / 24)
            if volume_spike > 10:
                green_flags.append("Volume 10x in 1H - momentum building")
        
        # Smart money analysis
        smart_wallets_buying = sum(1 for t in large_buys if self._is_smart_wallet(t.get("owner", "")))
        
        if smart_wallets_buying > 3:
            green_flags.append("Smart wallets accumulating")
        
        # Dev wallet check
        dev_address = security.get("owner_address", "")
        dev_sells = [t for t in trades if t.get("owner") == dev_address and t.get("type") == "sell"]
        
        if len(dev_sells) > 0:
            red_flags.append("Dev wallet selling - inside job risk")
        
        # Determine signal type
        if len(red_flags) > len(green_flags):
            signal_type = "dump"
            confidence = min(len(red_flags) / 5, 1.0)
            indicators = red_flags
        else:
            signal_type = "pump"
            confidence = min(len(green_flags) / 5, 1.0)
            indicators = green_flags
        
        return TokenSignal(
            token_address=token_address,
            token_name=overview.get("symbol", "Unknown"),
            signal_type=signal_type,
            confidence=confidence,
            indicators=indicators,
            timestamp=datetime.now().isoformat()
        )
    
    def _is_smart_wallet(self, wallet_address: str) -> bool:
        """Check if wallet has history of profitable early entries"""
        # Simplified - in production, maintain database of verified smart wallets
        # or check wallet's historical performance
        return len(wallet_address) > 30  # Placeholder logic
    
    # Alert & Monitoring
    
    def generate_alert_config(self, 
                            volume_threshold: float = 10000,
                            whale_threshold: float = 5000) -> Dict:
        """
        Generate Telegram alert configuration
        Step 5: Alerts set karo
        """
        config = {
            "alert_types": [
                {
                    "name": "volume_spike",
                    "description": "Volume increases 10x in 1 hour",
                    "threshold": volume_threshold,
                    "enabled": True
                },
                {
                    "name": "whale_movement",
                    "description": "Whale buy/sell above threshold",
                    "threshold": whale_threshold,
                    "enabled": True
                },
                {
                    "name": "new_token_launch",
                    "description": "Token launched <1h ago with liquidity",
                    "min_liquidity": 2000,
                    "enabled": True
                },
                {
                    "name": "lp_change",
                    "description": "LP pool changes >20%",
                    "threshold_percent": 20,
                    "enabled": True
                },
                {
                    "name": "holder_spike",
                    "description": "Holder count increases >1000 in 24h",
                    "threshold": 1000,
                    "enabled": True
                }
            ],
            "notification_method": "telegram",
            "check_interval_seconds": 60
        }
        return config
    
    # Practical Workflow Implementation
    
    def run_daily_scan(self, chains: List[str] = None) -> Dict:
        """
        Complete daily scan workflow as described in requirements
        Practical Workflow: aaj pump pakdna hai toh
        Enhanced to include profitable traders, wallet PnL, and security checks
        """
        if chains is None:
            chains = ["solana"]  # Default to solana
        
        results = {
            "timestamp": datetime.now().isoformat(),
            "trending_analysis": [],
            "whale_trades": [],
            "hidden_gems": [],
            "watchlist_updates": [],
            "profitable_traders": {},
            "security_alerts": []
        }
        
        # 1. Get profitable traders for each chain
        for chain in chains:
            try:
                traders = self.api.get_profitable_traders(chain=chain, time_frame="7D", limit=20)
                if traders and "error" not in traders[0]:
                    results["profitable_traders"][chain] = traders
            except Exception as e:
                results["profitable_traders"][chain] = {"error": str(e)}
        
        # 2. Check trending tokens (24H)
        trending = self.api.get_trending_tokens(time_frame="24h")
        
        for token in trending[:20]:
            token_address = token.get("address", "")
            if not token_address:
                continue
            
            # Security check BEFORE scoring (TASK 4)
            security = self.api.get_token_security(token_address)
            rug_risk = 0
            risk_factors = []
            
            is_mintable = security.get("is_mintable", False)
            freeze_authority = security.get("freeze_authority", False)
            top10_holder_pct = security.get("top_10_holder_percent", 0)
            
            if is_mintable:
                rug_risk += 30
                risk_factors.append("mintable")
            if freeze_authority:
                rug_risk += 25
                risk_factors.append("freeze_authority")
            if top10_holder_pct > 50:
                rug_risk += 25
            if top10_holder_pct > 80:
                rug_risk += 20
            
            # Add security alert for high-risk tokens
            if rug_risk >= 50:
                results["security_alerts"].append({
                    "token": token.get("symbol", "Unknown"),
                    "address": token_address,
                    "rug_risk_score": rug_risk,
                    "risk_factors": risk_factors,
                    "risk_level": "HIGH"
                })
            
            # Analyze for unusual activity
            signal = self.analyze_pump_dump_signals(token_address)
            signal_dict = signal.to_dict()
            signal_dict["rug_risk_score"] = rug_risk
            
            results["trending_analysis"].append({
                "token": token.get("symbol"),
                "address": token_address,
                "signal": signal_dict
            })
        
        # 3. Find whale trades with PnL enrichment (TASK 2)
        whale_trades = self.find_whale_trades(min_value_usd=10000)
        for trade in whale_trades[:10]:
            wallet = trade.get("wallet", "")
            if wallet:
                try:
                    pnl_data = self.api.get_wallet_pnl(wallet)
                    trade["pnl_summary"] = {
                        "realized_profit": pnl_data.get("realized_profit", 0),
                        "unrealized_profit": pnl_data.get("unrealized_profit", 0),
                        "win_rate": pnl_data.get("win_rate", 0),
                        "total_trades": pnl_data.get("total_trades", 0)
                    }
                except:
                    pass
        results["whale_trades"] = whale_trades[:10]
        
        # 4. Scan for hidden gems (already includes security filtering)
        gems = self.find_hidden_gems()
        results["hidden_gems"] = gems[:10]
        
        # 5. Update watchlist wallets with PnL
        for wallet_addr in self.watchlist:
            wallet_data = self.analyze_wallet(wallet_addr)
            try:
                pnl_data = self.api.get_wallet_pnl(wallet_addr)
                pnl_summary = {
                    "realized_profit": pnl_data.get("realized_profit", 0),
                    "unrealized_profit": pnl_data.get("unrealized_profit", 0),
                    "win_rate": pnl_data.get("win_rate", 0),
                    "total_trades": pnl_data.get("total_trades", 0)
                }
            except:
                pnl_summary = {}
            
            results["watchlist_updates"].append({
                "wallet": wallet_addr,
                "total_holdings": wallet_data.total_holdings,
                "top_tokens": wallet_data.most_held_tokens[:5],
                "pnl_summary": pnl_summary
            })
        
        return results
    
    def format_report(self, scan_results: Dict) -> str:
        """Format scan results into readable report"""
        report = [
            "=" * 60,
            f"BIRDEYE WHALE TRACKING REPORT",
            f"Generated: {scan_results['timestamp']}",
            "=" * 60,
            ""
        ]
        
        # Trending Analysis
        report.append("📊 TRENDING TOKENS ANALYSIS")
        report.append("-" * 60)
        for item in scan_results["trending_analysis"][:5]:
            signal = item["signal"]
            emoji = "🚀" if signal["signal_type"] == "pump" else "⚠️"
            report.append(f"{emoji} {item['token']}")
            report.append(f"   Signal: {signal['signal_type'].upper()} (confidence: {signal['confidence']:.0%})")
            report.append(f"   Indicators: {', '.join(signal['indicators'][:3])}")
            report.append("")
        
        # Whale Trades
        report.append("\n🐋 TOP WHALE TRADES")
        report.append("-" * 60)
        for trade in scan_results["whale_trades"][:5]:
            report.append(f"${trade['value_usd']:,.0f} - {trade['type'].upper()} {trade['token']}")
            report.append(f"   Wallet: {trade['wallet'][:8]}...{trade['wallet'][-6:]}")
            report.append("")
        
        # Hidden Gems
        report.append("\n💎 HIDDEN GEMS")
        report.append("-" * 60)
        for gem in scan_results["hidden_gems"][:5]:
            report.append(f"{gem['token']} (Score: {gem['score']:.0f}/100)")
            report.append(f"   Age: {gem['age_hours']:.1f}h | Volume 1H: ${gem['volume_1h_usd']:,.0f}")
            report.append(f"   Liquidity: ${gem['liquidity_usd']:,.0f} | Holders: {gem['holder_count']}")
            report.append("")
        
        return "\n".join(report)


# Utility functions for agent integration

def track_whale(wallet_address: str, api_key: Optional[str] = None) -> str:
    """Add whale wallet to tracking list"""
    tracker = WhaleTracker(api_key)
    result = tracker.add_to_watchlist(wallet_address)
    wallet_data = tracker.analyze_wallet(wallet_address)
    
    return f"{result}\n\nWallet Analysis:\n" + json.dumps(wallet_data.to_dict(), indent=2)


def find_pumps(api_key: Optional[str] = None) -> str:
    """Find potential pump tokens"""
    tracker = WhaleTracker(api_key)
    gems = tracker.find_hidden_gems()
    
    if not gems:
        return "No hidden gems found matching criteria"
    
    result = ["🔍 POTENTIAL PUMP TOKENS\n"]
    for i, gem in enumerate(gems[:10], 1):
        result.append(f"{i}. {gem['token']} - Score: {gem['score']:.0f}/100")
        result.append(f"   ${gem['volume_1h_usd']:,.0f} vol | {gem['age_hours']:.1f}h old")
    
    return "\n".join(result)


def analyze_token(token_address: str, api_key: Optional[str] = None) -> str:
    """Analyze token for pump/dump signals"""
    tracker = WhaleTracker(api_key)
    signal = tracker.analyze_pump_dump_signals(token_address)
    
    emoji = "🚀" if signal.signal_type == "pump" else "⚠️"
    
    result = [
        f"{emoji} TOKEN SIGNAL ANALYSIS",
        f"Token: {signal.token_name}",
        f"Signal: {signal.signal_type.upper()}",
        f"Confidence: {signal.confidence:.0%}",
        "",
        "Indicators:"
    ]
    
    for indicator in signal.indicators:
        result.append(f"  • {indicator}")
    
    return "\n".join(result)


def daily_scan(api_key: Optional[str] = None, chains: List[str] = None, save_json: bool = True) -> str:
    """Run complete daily whale tracking scan and save JSON report"""
    tracker = WhaleTracker(api_key)
    
    if chains is None:
        chains = ["solana"]  # Default to solana
    
    results = tracker.run_daily_scan(chains=chains)
    
    # Save structured JSON report (TASK 6)
    if save_json:
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_path = f"reports/daily_scan_{timestamp}.json"
        
        try:
            os.makedirs("reports", exist_ok=True)
            with open(json_path, "w") as f:
                json.dump(results, f, indent=2, default=str)
        except Exception as e:
            pass  # Silently fail if can't write
    
    return tracker.format_report(results)


def get_profitable_traders(chain: str = "solana", time_frame: str = "7D", api_key: Optional[str] = None, save_report: bool = True) -> str:
    """Get profitable traders leaderboard and save to reports folder"""
    tracker = WhaleTracker(api_key)
    traders = tracker.api.get_profitable_traders(chain=chain, time_frame=time_frame)
    
    if not traders or "error" in traders[0]:
        return f"Error fetching profitable traders: {traders}"
    
    # Save to reports folder (TASK 1)
    if save_report:
        try:
            os.makedirs("reports", exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d")
            json_path = f"reports/profitable_traders_{timestamp}.json"
            with open(json_path, "w") as f:
                json.dump({"chain": chain, "time_frame": time_frame, "traders": traders}, f, indent=2)
        except Exception as e:
            pass  # Silently fail if can't write
    
    result = [f"🏆 TOP PROFITABLE TRADERS ({chain.upper()}, {time_frame})\n"]
    for i, t in enumerate(traders[:20], 1):
        pnl = t.get("pnl", 0)
        volume = t.get("volume", 0)
        wallet = t.get("wallet_address", t.get("address", "unknown"))
        trades = t.get("trade_count", t.get("trades", 0))
        result.append(f"{i}. {wallet[:8]}...{wallet[-6:]}")
        result.append(f"   PnL: ${pnl:,.2f} | Volume: ${volume:,.2f} | Trades: {trades}")
    
    return "\n".join(result)


def get_wallet_pnl(wallet_address: str, chain: str = "solana", api_key: Optional[str] = None) -> str:
    """Get wallet PnL summary"""
    tracker = WhaleTracker(api_key)
    pnl_data = tracker.api.get_wallet_pnl(wallet_address, chain=chain)
    
    if not pnl_data or "error" in pnl_data:
        return f"Error fetching wallet PnL: {pnl_data}"
    
    realized = pnl_data.get("realized_profit", 0)
    unrealized = pnl_data.get("unrealized_profit", 0)
    win_rate = pnl_data.get("win_rate", 0) * 100
    total_trades = pnl_data.get("total_trades", 0)
    
    result = [
        f"💰 WALLET PnL SUMMARY ({chain.upper()})",
        f"Wallet: {wallet_address[:8]}...{wallet_address[-6:]}",
        "",
        f"Realized Profit: ${realized:,.2f}",
        f"Unrealized Profit: ${unrealized:,.2f}",
        f"Total PnL: ${realized + unrealized:,.2f}",
        f"Win Rate: {win_rate:.1f}%",
        f"Total Trades: {total_trades}"
    ]
    
    return "\n".join(result)


def get_top_traders(token_address: str, chain: str = "solana", time_frame: str = "24h", api_key: Optional[str] = None) -> str:
    """Get top traders for a token"""
    tracker = WhaleTracker(api_key)
    traders = tracker.api.get_top_traders(token_address, chain=chain, time_frame=time_frame)
    
    if not traders or "error" in traders[0]:
        return f"Error fetching top traders: {traders}"
    
    result = [f"📊 TOP TRADERS FOR TOKEN ({chain.upper()}, {time_frame})\n"]
    for i, t in enumerate(traders[:10], 1):
        wallet = t.get("wallet_address", t.get("address", "unknown"))
        volume = t.get("volume", 0)
        pnl = t.get("pnl", 0)
        buys = t.get("buy_count", 0)
        sells = t.get("sell_count", 0)
        result.append(f"{i}. {wallet[:8]}...{wallet[-6:]}")
        result.append(f"   Volume: ${volume:,.2f} | PnL: ${pnl:,.2f} | Buys: {buys} | Sells: {sells}")
    
    return "\n".join(result)


def check_token_security(token_address: str, chain: str = "solana", api_key: Optional[str] = None) -> str:
    """Check token security and return risk assessment"""
    tracker = WhaleTracker(api_key)
    security = tracker.api.get_token_security(token_address)
    
    if not security or "error" in security:
        return f"Error fetching token security: {security}"
    
    is_mintable = security.get("is_mintable", False)
    freeze_authority = security.get("freeze_authority", False)
    top10_holder_pct = security.get("top_10_holder_percent", 0)
    
    # Calculate rug risk score
    rug_risk = 0
    risk_factors = []
    
    if is_mintable:
        rug_risk += 30
        risk_factors.append("Mintable supply")
    if freeze_authority:
        rug_risk += 25
        risk_factors.append("Freeze authority enabled")
    if top10_holder_pct > 50:
        rug_risk += 25
        risk_factors.append(f"Top 10 holders: {top10_holder_pct}%")
    if top10_holder_pct > 80:
        rug_risk += 20
        risk_factors.append("Extremely concentrated holdings")
    
    risk_level = "HIGH" if rug_risk >= 50 else "MEDIUM" if rug_risk >= 25 else "LOW"
    emoji = "🔴" if risk_level == "HIGH" else "🟡" if risk_level == "MEDIUM" else "🟢"
    
    result = [
        f"{emoji} TOKEN SECURITY CHECK ({chain.upper()})",
        f"Token: {token_address[:8]}...{token_address[-6:]}",
        "",
        f"Risk Level: {risk_level} (Score: {rug_risk}/100)",
        "",
        f"Is Mintable: {'Yes ⚠️' if is_mintable else 'No ✅'}",
        f"Freeze Authority: {'Yes ⚠️' if freeze_authority else 'No ✅'}",
        f"Top 10 Holder %: {top10_holder_pct}%",
        "",
        f"Risk Factors: {', '.join(risk_factors) if risk_factors else 'None detected'}"
    ]
    
    return "\n".join(result)


# New utility functions for additional Birdeye features

def get_new_listings(chain: str = "solana", limit: int = 50, api_key: Optional[str] = None) -> str:
    """Get newly listed tokens"""
    tracker = WhaleTracker(api_key)
    listings = tracker.api.get_new_listings(chain=chain, limit=limit)
    
    if not listings or "error" in listings[0]:
        return f"Error fetching new listings: {listings}"
    
    result = [f"🆕 NEW LISTINGS ({chain.upper()})\n"]
    for i, token in enumerate(listings[:20], 1):
        symbol = token.get("symbol", "Unknown")
        address = token.get("address", "")[:8] + "..." + token.get("address", "")[-6:]
        created = token.get("created_at", 0)
        age_min = round((time.time() - created) / 60, 1) if created else "?"
        result.append(f"{i}. {symbol} ({address}) — {age_min} min old")
    
    return "\n".join(result)


def get_token_creation_info(token_address: str, chain: str = "solana", api_key: Optional[str] = None) -> str:
    """Get token creation info"""
    tracker = WhaleTracker(api_key)
    info = tracker.api.get_token_creation_info(token_address, chain=chain)
    
    if not info or "error" in info:
        return f"Error fetching creation info: {info}"
    
    deployer = info.get("deployer", "")[:8] + "..." + info.get("deployer", "")[-6:] if info.get("deployer") else "Unknown"
    created_at = info.get("created_at", 0)
    initial_supply = info.get("initial_supply", 0)
    
    return f"📜 TOKEN CREATION INFO\nToken: {token_address[:8]}...{token_address[-6:]}\nDeployer: {deployer}\nCreated: {datetime.fromtimestamp(created_at).isoformat() if created_at else 'Unknown'}\nInitial Supply: {initial_supply}"


def get_holder_list(token_address: str, chain: str = "solana", limit: int = 100, api_key: Optional[str] = None) -> str:
    """Get token holder list"""
    tracker = WhaleTracker(api_key)
    holders = tracker.api.get_holder_list(token_address, chain=chain, limit=limit)
    
    if not holders or "error" in holders[0]:
        return f"Error fetching holders: {holders}"
    
    result = [f"💼 TOP HOLDERS ({token_address[:8]}...)\n"]
    for i, h in enumerate(holders[:10], 1):
        wallet = h.get("owner", "")[:8] + "..." + h.get("owner", "")[-6:]
        balance = h.get("balance", 0)
        pct = h.get("percent", 0)
        result.append(f"{i}. {wallet} — {pct:.2f}% ({balance:,.0f})")
    
    return "\n".join(result)


def get_wallet_pnl_details(wallet_address: str, chain: str = "solana", limit: int = 100, api_key: Optional[str] = None) -> str:
    """Get detailed PnL breakdown per token"""
    tracker = WhaleTracker(api_key)
    details = tracker.api.get_wallet_pnl_details(wallet_address, chain=chain, limit=limit)
    
    if not details or "error" in details[0]:
        return f"Error fetching PnL details: {details}"
    
    result = [f"📊 WALLET PnL DETAILS ({wallet_address[:8]}...)\n"]
    total_pnl = 0
    for d in details[:15]:
        token = d.get("token_symbol", "Unknown")
        pnl = d.get("realized_pnl", 0)
        total_pnl += pnl
        color = "🟢" if pnl > 0 else "🔴" if pnl < 0 else "⚪"
        result.append(f"{color} {token}: ${pnl:,.2f}")
    
    result.append(f"\nTotal PnL: ${total_pnl:,.2f}")
    return "\n".join(result)


def get_trader_txs(wallet_address: str, chain: str = "solana", start_time: int = None, end_time: int = None, limit: int = 50, api_key: Optional[str] = None) -> str:
    """Get trader transaction history"""
    tracker = WhaleTracker(api_key)
    txs = tracker.api.get_trader_txs(wallet_address, chain=chain, start_time=start_time, end_time=end_time, limit=limit)
    
    if not txs or "error" in txs[0]:
        return f"Error fetching transactions: {txs}"
    
    result = [f"📜 TRADER TX HISTORY ({wallet_address[:8]}...)\n"]
    for tx in txs[:10]:
        tx_type = tx.get("type", "?").upper()
        token = tx.get("token_symbol", "?")
        value = tx.get("value_usd", 0)
        result.append(f"{tx_type} {token} — ${value:,.2f}")
    
    return "\n".join(result)


def get_ohlcv(token_address: str, chain: str = "solana", timeframe: str = "1h", api_key: Optional[str] = None) -> str:
    """Get OHLCV candle data"""
    tracker = WhaleTracker(api_key)
    candles = tracker.api.get_ohlcv(token_address, chain=chain, timeframe=timeframe)
    
    if not candles or "error" in candles[0]:
        return f"Error fetching OHLCV: {candles}"
    
    result = [f"📈 OHLCV ({token_address[:8]}..., {timeframe})\n"]
    for c in candles[-5:]:
        t = datetime.fromtimestamp(c.get("time", 0)).strftime("%m/%d %H:%M")
        o, h, l, cl = c.get("o", 0), c.get("h", 0), c.get("l", 0), c.get("c", 0)
        result.append(f"{t} | O:{o:.6f} H:{h:.6f} L:{l:.6f} C:{cl:.6f}")
    
    return "\n".join(result)


def get_wallet_token_list(wallet_address: str, chain: str = "solana", api_key: Optional[str] = None) -> str:
    """Get wallet token holdings"""
    tracker = WhaleTracker(api_key)
    tokens = tracker.api.get_wallet_token_list(wallet_address, chain=chain)
    
    if not tokens or "error" in tokens[0]:
        return f"Error fetching token list: {tokens}"
    
    result = [f"💼 WALLET HOLDINGS ({wallet_address[:8]}...)\n"]
    total = 0
    for t in tokens[:15]:
        symbol = t.get("symbol", "?")
        value = float(t.get("value_usd", 0))
        total += value
        result.append(f"{symbol}: ${value:,.2f}")
    
    result.append(f"\nTotal: ${total:,.2f}")
    return "\n".join(result)


def get_wallet_tx_list(wallet_address: str, chain: str = "solana", page: int = 1, page_size: int = 20, api_key: Optional[str] = None) -> str:
    """Get wallet transaction list"""
    tracker = WhaleTracker(api_key)
    txs = tracker.api.get_wallet_tx_list(wallet_address, chain=chain, page=page, page_size=page_size)
    
    if not txs or "error" in txs[0]:
        return f"Error fetching tx list: {txs}"
    
    result = [f"📜 WALLET TRANSACTIONS ({wallet_address[:8]}...)\n"]
    for tx in txs[:10]:
        sig = tx.get("signature", "")[:8] + "..."
        tx_type = tx.get("type", "?").upper()
        time_str = datetime.fromtimestamp(tx.get("block_time", 0)).strftime("%m/%d %H:%M") if tx.get("block_time") else "?"
        result.append(f"[{time_str}] {sig} — {tx_type}")
    
    return "\n".join(result)

