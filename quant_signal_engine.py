"""
Birdeye Quant Signal Engine

Live-data pipeline for token discovery, snapshot storage, and pump/dump
signal scoring. It uses Birdeye's public API instead of scraping pages.
"""

from __future__ import annotations

import argparse
import logging
import csv
import json
import math
import os
import re
import sqlite3
import statistics
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import requests


# AzalystClient uses DexScreener + GeckoTerminal + GoPlus + Helius
BINANCE_FUTURES_EXCHANGE_INFO_URL = "https://fapi.binance.com/fapi/v1/exchangeInfo"  # kept for BinanceFuturesUniverse
DEFAULT_DB = Path("data") / "birdeye_quant.db"
DEFAULT_REPORT_DIR = Path("reports")
DEFAULT_BINANCE_CACHE = Path("data") / "binance_usdt_futures_cache.json"

SUPPORTED_CHAINS = {
    "solana": "solana",
    "ethereum": "ethereum",
    "base": "base",
    "arbitrum": "arbitrum",
    "bnb": "bsc",
    "bsc": "bsc",
    "avalanche": "avalanche",
    "polygon": "polygon",
    "optimism": "optimism",
    "zksync": "zksync",
}

DEFAULT_SCAN_CHAINS = [
    "solana",
    "ethereum",
    "base",
    "arbitrum",
    "bnb",
    "avalanche",
    "polygon",
    "optimism",
    "zksync",
]

BINANCE_BASE_ASSET_ALIASES = {
    "BTC": ["WBTC", "XBT"],
    "ETH": ["WETH", "BETH"],
    "BNB": ["WBNB"],
    "SOL": ["WSOL"],
    "DOGE": ["WDOGE"],
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_utc(value: str) -> datetime:
    text = (value or "").replace("Z", "+00:00")
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def to_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        if isinstance(value, str):
            value = value.replace(",", "").replace("$", "").replace("%", "")
        out = float(value)
        if math.isnan(out) or math.isinf(out):
            return default
        return out
    except (TypeError, ValueError):
        return default


def to_int(value: Any, default: int = 0) -> int:
    return int(to_float(value, float(default)))


def flag_int(value: Any) -> int:
    if isinstance(value, dict):
        for key in ("status", "value", "enabled", "result"):
            if key in value:
                return flag_int(value.get(key))
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"", "0", "false", "no", "off", "null", "none"}:
            return 0
        if normalized in {"1", "true", "yes", "on"}:
            return 1
    return 1 if to_float(value, 0.0) != 0 else 0


def first_value(data: Dict[str, Any], keys: Sequence[str], default: Any = None) -> Any:
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return data[key]
    return default


def first_float(data: Dict[str, Any], keys: Sequence[str], default: float = 0.0) -> float:
    return to_float(first_value(data, keys, default), default)


def first_int(data: Dict[str, Any], keys: Sequence[str], default: int = 0) -> int:
    return to_int(first_value(data, keys, default), default)


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def pct_change(current: float, previous: float) -> float:
    if previous == 0:
        return 0.0
    return (current - previous) / abs(previous) * 100.0


def log1p_pos(value: float) -> float:
    return math.log1p(max(value, 0.0))


def robust_z(value: float, sample: Sequence[float]) -> float:
    values = [v for v in sample if v is not None and not math.isnan(v)]
    if len(values) < 5:
        return 0.0
    med = statistics.median(values)
    deviations = [abs(v - med) for v in values]
    mad = statistics.median(deviations)
    if mad <= 1e-12:
        return 0.0
    return 0.6745 * (value - med) / mad


def parse_chains(raw: str) -> List[str]:
    items = [item.strip().lower() for item in (raw or "").split(",") if item.strip()]
    if not items or any(item in {"all", "*", "any"} for item in items):
        return list(DEFAULT_SCAN_CHAINS)

    chains = []
    seen = set()
    for chain in items:
        if chain not in SUPPORTED_CHAINS:
            raise ValueError(f"Unsupported chain '{chain}'. Supported: {', '.join(SUPPORTED_CHAINS)}")
        if chain in seen:
            continue
        seen.add(chain)
        chains.append(chain)
    return chains or list(DEFAULT_SCAN_CHAINS)


def compact_address(address: str) -> str:
    if not address:
        return "?"
    if len(address) <= 14:
        return address
    return f"{address[:6]}...{address[-4:]}"


def console_safe(text: Any) -> str:
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        return str(text).encode(encoding, errors="replace").decode(encoding, errors="replace")
    except Exception:
        return str(text).encode("ascii", errors="replace").decode("ascii", errors="replace")


def normalize_symbol(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


class BinanceFuturesUniverse:
    def __init__(self, timeout: int = 20, cache_path: Optional[Path] = None):
        self.timeout = timeout
        self.cache_path = cache_path or DEFAULT_BINANCE_CACHE
        self.session = requests.Session()
        self._lookup: Dict[str, Dict[str, Any]] = {}
        self.last_source = "unknown"

    def refresh(self) -> Dict[str, Dict[str, Any]]:
        try:
            response = self.session.get(
                BINANCE_FUTURES_EXCHANGE_INFO_URL,
                headers={"Accept": "application/json"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
            lookup = self._build_lookup(payload.get("symbols", []))
            self._write_cache(payload.get("symbols", []))
            self.last_source = "live"
            self._lookup = lookup
            return lookup
        except Exception:
            cached = self._read_cache()
            if cached:
                self.last_source = "cache"
                self._lookup = cached
                return cached
            raise

    def _build_lookup(self, symbols: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        lookup: Dict[str, Dict[str, Any]] = {}
        for item in symbols:
            if str(item.get("quoteAsset") or "").upper() != "USDT":
                continue
            if str(item.get("status") or "").upper() != "TRADING":
                continue

            base_asset = normalize_symbol(item.get("baseAsset"))
            binance_symbol = str(item.get("symbol") or "")
            if not base_asset or not binance_symbol:
                continue

            meta = {
                "binance_usdt_futures": True,
                "binance_symbol": binance_symbol,
                "binance_base_asset": str(item.get("baseAsset") or ""),
                "binance_contract_type": str(item.get("contractType") or ""),
            }
            self._register_lookup(lookup, base_asset, meta, "base_asset")

            stripped = re.sub(r"^(?:1M|\d+)", "", base_asset)
            if stripped and stripped != base_asset:
                self._register_lookup(lookup, stripped, meta, "contract_multiplier")

            for alias in BINANCE_BASE_ASSET_ALIASES.get(base_asset, []):
                self._register_lookup(lookup, alias, meta, "wrapped_alias")
        return lookup

    def _write_cache(self, symbols: Sequence[Dict[str, Any]]) -> None:
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "fetched_at": utc_now(),
                "symbols": [
                    {
                        "symbol": item.get("symbol"),
                        "baseAsset": item.get("baseAsset"),
                        "quoteAsset": item.get("quoteAsset"),
                        "status": item.get("status"),
                        "contractType": item.get("contractType"),
                    }
                    for item in symbols
                ],
            }
            self.cache_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _read_cache(self) -> Dict[str, Dict[str, Any]]:
        try:
            if not self.cache_path.exists():
                return {}
            payload = json.loads(self.cache_path.read_text(encoding="utf-8-sig"))
            return self._build_lookup(payload.get("symbols", []))
        except Exception:
            return {}

    def _register_lookup(
        self,
        lookup: Dict[str, Dict[str, Any]],
        key: str,
        meta: Dict[str, Any],
        match_type: str,
    ) -> None:
        normalized = normalize_symbol(key)
        if not normalized or normalized in lookup:
            return
        lookup[normalized] = {**meta, "binance_match_type": match_type}

    def match_token(self, symbol: str) -> Optional[Dict[str, Any]]:
        if not self._lookup:
            self.refresh()

        normalized = normalize_symbol(symbol)
        if not normalized:
            return None
        if normalized in self._lookup:
            return dict(self._lookup[normalized])

        if normalized.startswith("W") and normalized[1:] in self._lookup:
            match = dict(self._lookup[normalized[1:]])
            match["binance_match_type"] = "wrapped_prefix"
            return match

        return None


# ---------------------------------------------------------------------------
# AzalystClient — drop-in replacement for BirdeyeClient
# Sources: DexScreener + GeckoTerminal + GoPlus + Helius (Solana)
#
# Paste this block (constants + class) into quant_signal_engine.py to replace
# the BirdeyeClient class that lives at lines 284-418.
# Do NOT include the import statements below; the host file already has them.
# ---------------------------------------------------------------------------

_DS_BASE = "https://api.dexscreener.com"
_GT_BASE = "https://api.geckoterminal.com/api/v2"
_GP_BASE = "https://api.gopluslabs.io/api/v1"
_HELIUS_RPC = "https://mainnet.helius-rpc.com"
_HELIUS_API = "https://api.helius.xyz/v0"

_GT_NETWORK = {
    "solana": "solana",
    "ethereum": "eth",
    "base": "base",
    "arbitrum": "arbitrum",
    "bnb": "bsc",
    "avalanche": "avax",
    "polygon": "polygon_pos",
    "optimism": "optimism",
    "zksync": "zksync",
}

_DS_CHAIN = {
    "solana": "solana",
    "ethereum": "ethereum",
    "base": "base",
    "arbitrum": "arbitrum",
    "bnb": "bsc",
    "avalanche": "avalanche",
    "polygon": "polygon",
    "optimism": "optimism",
    "zksync": "zksync",
}

_GP_CHAIN_ID = {
    "ethereum": "1",
    "bnb": "56",
    "polygon": "137",
    "avalanche": "43114",
    "arbitrum": "42161",
    "base": "8453",
    "optimism": "10",
    "zksync": "324",
    "solana": "solana",
}


class AzalystClient:
    """
    Multi-source crypto data client for Azalyst Alpha Scanner.
    Drop-in replacement for BirdeyeClient — identical public API.

    Data sources:
      - DexScreener  (no key required)
      - GeckoTerminal (no key required)
      - GoPlus        (no key required)
      - Helius        (api_key = HELIUS_API_KEY, Solana only)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        min_delay: float = 0.15,
        timeout: int = 20,
    ) -> None:
        self.api_key: str = api_key or os.environ.get("HELIUS_API_KEY", "")
        self.min_delay = min_delay
        self.timeout = timeout
        self._last_call: float = 0.0
        self._pair_cache: Dict[str, str] = {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _throttle(self) -> None:
        elapsed = time.time() - self._last_call
        if elapsed < self.min_delay:
            time.sleep(self.min_delay - elapsed)
        self._last_call = time.time()

    def _get(self, url: str, params: Optional[Dict] = None) -> Optional[Dict]:
        last_exc: Optional[Exception] = None
        for attempt in range(3):
            self._throttle()
            try:
                resp = requests.get(url, params=params, timeout=self.timeout)
                resp.raise_for_status()
                return resp.json()
            except requests.HTTPError as exc:
                last_exc = exc
                if exc.response is not None and exc.response.status_code == 429 and attempt < 2:
                    retry_after = to_float(exc.response.headers.get("Retry-After"), 0.0)
                    time.sleep(max(retry_after, self.min_delay * (attempt + 2), 1.0))
                    continue
                break
            except Exception as exc:
                last_exc = exc
                break
        logging.getLogger("azalyst_client").warning("GET %s failed: %s", url, last_exc)
        return None

    def _post(self, url: str, payload: Dict) -> Optional[Dict]:
        self._throttle()
        try:
            resp = requests.post(url, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logging.getLogger("azalyst_client").warning("POST %s failed: %s", url, exc)
            return None

    @staticmethod
    def _sf(value: Any, default: float = 0.0) -> float:
        """Safe float conversion."""
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _resolve_pair(self, chain: str, address: str) -> str:
        """Return DexScreener pair address for *address*, using cache when available."""
        cached = self._pair_cache.get(address)
        if cached:
            return cached
        overview = self.token_overview(chain, address)
        return self._pair_cache.get(address, "")

    # ------------------------------------------------------------------
    # token_trending
    # ------------------------------------------------------------------
    def token_trending(
        self,
        chain: str,
        limit: int = 50,
        sort_by: str = "volume",
    ) -> List[Dict]:
        """
        Return trending tokens via GeckoTerminal trending_pools.
        Each item is guaranteed to have an `address` key.
        """
        network = _GT_NETWORK.get(chain.lower())
        if not network:
            return []

        url = f"{_GT_BASE}/networks/{network}/trending_pools"
        data = self._get(url, params={"include": "base_token"})
        if not data:
            return []

        results: List[Dict] = []
        for pool in (data.get("data") or [])[:limit]:
            attrs = pool.get("attributes", {})
            relationships = pool.get("relationships", {})
            base_data = relationships.get("base_token", {}).get("data", {})

            address = ""
            if base_data:
                token_id = base_data.get("id", "")
                parts = token_id.split("_", 1)
                address = parts[1] if len(parts) == 2 else token_id

            vol = attrs.get("volume_usd", {})
            price_chg = attrs.get("price_change_percentage", {})

            results.append({
                "address": address,
                "symbol": attrs.get("name", "").split(" / ")[0],
                "name": attrs.get("name", ""),
                "price": self._sf(attrs.get("base_token_price_usd")),
                "liquidity_usd": self._sf(attrs.get("reserve_in_usd")),
                "v24h": self._sf(vol.get("h24") if isinstance(vol, dict) else vol),
                "v1h": self._sf(vol.get("h1") if isinstance(vol, dict) else 0),
                "price_change_24h_pct": self._sf(
                    price_chg.get("h24") if isinstance(price_chg, dict) else 0
                ),
                "price_change_1h_pct": self._sf(
                    price_chg.get("h1") if isinstance(price_chg, dict) else 0
                ),
                "fdv": 0.0,
                "mc": 0.0,
                "chain": chain,
            })
        return results

    # ------------------------------------------------------------------
    # token_list
    # ------------------------------------------------------------------
    def token_list(
        self,
        chain: str,
        limit: int = 50,
        sort_by: str = "v24hUSD",
        min_liquidity: float = 0.0,
    ) -> List[Dict]:
        """
        Return top tokens via GeckoTerminal top pools (by volume).
        Each item is guaranteed to have an `address` key.
        """
        network = _GT_NETWORK.get(chain.lower())
        if not network:
            return []

        # GeckoTerminal does not have a generic "top tokens" endpoint;
        # trending_pools ordered by volume is the closest equivalent.
        url = f"{_GT_BASE}/networks/{network}/pools"
        data = self._get(url, params={"include": "base_token", "page": 1})
        if not data:
            # Fallback to trending
            data = self._get(
                f"{_GT_BASE}/networks/{network}/trending_pools",
                params={"include": "base_token"},
            )
        if not data:
            return []

        results: List[Dict] = []
        for pool in (data.get("data") or [])[:limit]:
            attrs = pool.get("attributes", {})
            liq = self._sf(attrs.get("reserve_in_usd"))
            if liq < min_liquidity:
                continue

            relationships = pool.get("relationships", {})
            base_data = relationships.get("base_token", {}).get("data", {})
            address = ""
            if base_data:
                token_id = base_data.get("id", "")
                parts = token_id.split("_", 1)
                address = parts[1] if len(parts) == 2 else token_id

            vol = attrs.get("volume_usd", {})
            price_chg = attrs.get("price_change_percentage", {})

            results.append({
                "address": address,
                "symbol": attrs.get("name", "").split(" / ")[0],
                "name": attrs.get("name", ""),
                "price": self._sf(attrs.get("base_token_price_usd")),
                "liquidity_usd": liq,
                "v24h": self._sf(vol.get("h24") if isinstance(vol, dict) else vol),
                "v1h": self._sf(vol.get("h1") if isinstance(vol, dict) else 0),
                "price_change_24h_pct": self._sf(
                    price_chg.get("h24") if isinstance(price_chg, dict) else 0
                ),
                "price_change_1h_pct": self._sf(
                    price_chg.get("h1") if isinstance(price_chg, dict) else 0
                ),
                "fdv": 0.0,
                "mc": 0.0,
                "chain": chain,
            })
        return results

    # ------------------------------------------------------------------
    # new_listings
    # ------------------------------------------------------------------
    def new_listings(self, chain: str, limit: int = 50) -> List[Dict]:
        """
        Return newly listed tokens via GeckoTerminal new_pools.
        Each item is guaranteed to have an `address` key.
        """
        network = _GT_NETWORK.get(chain.lower())
        if not network:
            return []

        url = f"{_GT_BASE}/networks/{network}/new_pools"
        data = self._get(url, params={"include": "base_token"})
        if not data:
            return []

        results: List[Dict] = []
        for pool in (data.get("data") or [])[:limit]:
            attrs = pool.get("attributes", {})
            relationships = pool.get("relationships", {})
            base_data = relationships.get("base_token", {}).get("data", {})

            address = ""
            if base_data:
                token_id = base_data.get("id", "")
                parts = token_id.split("_", 1)
                address = parts[1] if len(parts) == 2 else token_id

            created_raw = attrs.get("pool_created_at", "")
            created_ts = 0
            if created_raw:
                try:
                    import datetime as _dt
                    created_ts = int(
                        _dt.datetime.fromisoformat(
                            created_raw.replace("Z", "+00:00")
                        ).timestamp()
                    )
                except Exception:
                    pass

            results.append({
                "address": address,
                "symbol": attrs.get("name", "").split(" / ")[0],
                "name": attrs.get("name", ""),
                "created_at": created_ts,
                "chain": chain,
                "price": self._sf(attrs.get("base_token_price_usd")),
                "liquidity_usd": self._sf(attrs.get("reserve_in_usd")),
            })
        return results

    # ------------------------------------------------------------------
    # token_overview
    # ------------------------------------------------------------------
    def token_overview(self, chain: str, address: str) -> Dict:
        """
        Return normalized token overview from DexScreener.

        All keys present so downstream `first_float` fallback logic works:
          price, liquidity_usd, fdv, mc, v5m, v1h, v24h,
          price_change_5m_pct, price_change_1h_pct, price_change_24h_pct,
          symbol, name, address, pair_address, holder, holder_change_24h
        """
        url = f"{_DS_BASE}/latest/dex/tokens/{address}"
        data = self._get(url)
        if not data:
            return {"error": "DexScreener request failed", "address": address}

        ds_chain = _DS_CHAIN.get(chain.lower(), chain.lower())
        pairs_raw = data.get("pairs") or []
        pairs = [
            p for p in pairs_raw
            if p.get("chainId", "").lower() == ds_chain
        ]
        if not pairs:
            pairs = pairs_raw
        if not pairs:
            return {"error": "No pairs found", "address": address}

        pairs.sort(
            key=lambda p: self._sf(p.get("liquidity", {}).get("usd", 0)),
            reverse=True,
        )
        pair = pairs[0]

        pair_address = pair.get("pairAddress", "")
        if pair_address:
            self._pair_cache[address] = pair_address

        base = pair.get("baseToken", {})
        liquidity = pair.get("liquidity", {})
        volume = pair.get("volume", {})
        price_change = pair.get("priceChange", {})

        return {
            "address": address,
            "symbol": base.get("symbol", ""),
            "name": base.get("name", ""),
            "price": self._sf(pair.get("priceUsd")),
            "liquidity_usd": self._sf(liquidity.get("usd")),
            "fdv": self._sf(pair.get("fdv")),
            "mc": self._sf(pair.get("marketCap")),
            "v5m": self._sf(volume.get("m5")),
            "v1h": self._sf(volume.get("h1")),
            "v24h": self._sf(volume.get("h24")),
            "price_change_5m_pct": self._sf(price_change.get("m5")),
            "price_change_1h_pct": self._sf(price_change.get("h1")),
            "price_change_24h_pct": self._sf(price_change.get("h24")),
            "pair_address": pair_address,
            "holder": 0,
            "holder_change_24h": 0,
        }

    # ------------------------------------------------------------------
    # token_security
    # ------------------------------------------------------------------
    def token_security(self, chain: str, address: str) -> Dict:
        """
        Return token security data via GoPlus.
        Keys: is_mintable, freeze_authority, top_10_holder_percent, owner_address
        """
        chain_id = _GP_CHAIN_ID.get(chain.lower())
        if not chain_id:
            return {
                "is_mintable": 0,
                "freeze_authority": "0",
                "top_10_holder_percent": 0.0,
                "owner_address": "",
            }

        if chain_id == "solana":
            url = f"{_GP_BASE}/solana/token_security"
            data = self._get(url, params={"contract_addresses": address})
        else:
            url = f"{_GP_BASE}/token_security/{chain_id}"
            data = self._get(url, params={"contract_addresses": address})

        if not data or data.get("code") != 1:
            return {
                "is_mintable": 0,
                "freeze_authority": "0",
                "top_10_holder_percent": 0.0,
                "owner_address": "",
            }

        result = data.get("result", {})
        info = result.get(address.lower()) or result.get(address) or {}

        if chain_id == "solana":
            return {
                "is_mintable": flag_int(info.get("mintable", 0)),
                "freeze_authority": str(flag_int(info.get("freezable", "0"))),
                "top_10_holder_percent": self._sf(info.get("top10HolderPercent")),
                "owner_address": info.get("ownerAddress", ""),
            }
        else:
            return {
                "is_mintable": flag_int(info.get("is_mintable", 0)),
                "freeze_authority": str(flag_int(info.get("owner_change_balance", "0"))),
                "top_10_holder_percent": self._sf(info.get("top10HolderRatio", 0)) * 100,
                "owner_address": info.get("owner_address", ""),
            }

    # ------------------------------------------------------------------
    # token_trades
    # ------------------------------------------------------------------
    def token_trades(
        self, chain: str, address: str, limit: int = 100
    ) -> List[Dict]:
        """
        Return recent trades via GeckoTerminal pool trades.
        Keys: type, side, value_usd, owner, block_unix_time
        """
        network = _GT_NETWORK.get(chain.lower())
        if not network:
            return []

        pair_address = self._pair_cache.get(address) or self._resolve_pair(chain, address)
        if not pair_address:
            return []

        url = f"{_GT_BASE}/networks/{network}/pools/{pair_address}/trades"
        data = self._get(url, params={"trade_volume_in_usd_greater_than": 0})
        if not data:
            return []

        trades = []
        for trade in (data.get("data") or [])[:limit]:
            attrs = trade.get("attributes", {})
            kind = attrs.get("kind", "buy")
            ts = 0
            raw_ts = attrs.get("block_timestamp", "")
            if raw_ts:
                try:
                    import datetime as _dt
                    ts = int(
                        _dt.datetime.fromisoformat(
                            raw_ts.replace("Z", "+00:00")
                        ).timestamp()
                    )
                except Exception:
                    pass
            trades.append({
                "type": "buy" if kind == "buy" else "sell",
                "side": kind,
                "value_usd": self._sf(attrs.get("volume_in_usd")),
                "owner": attrs.get("tx_from_address", ""),
                "block_unix_time": ts,
            })
        return trades

    # ------------------------------------------------------------------
    # holder_list
    # ------------------------------------------------------------------
    def holder_list(
        self, chain: str, address: str, limit: int = 50
    ) -> List[Dict]:
        """
        Return top holders.
        Helius getTokenLargestAccounts for Solana; GoPlus for EVM.
        Keys: owner, percent, balance
        """
        if chain.lower() == "solana":
            return self._helius_holders(address, limit)
        return self._goplus_holders(chain, address, limit)

    def _helius_holders(self, address: str, limit: int) -> List[Dict]:
        if not self.api_key:
            return []
        url = f"{_HELIUS_RPC}/?api-key={self.api_key}"
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTokenLargestAccounts",
            "params": [address],
        }
        data = self._post(url, payload)
        if not data:
            return []
        accounts = data.get("result", {}).get("value") or []
        total = sum(self._sf(a.get("uiAmount", 0)) for a in accounts)
        holders = []
        for acc in accounts[:limit]:
            amt = self._sf(acc.get("uiAmount", 0))
            holders.append({
                "owner": acc.get("address", ""),
                "percent": (amt / total * 100) if total > 0 else 0.0,
                "balance": amt,
            })
        return holders

    def _goplus_holders(self, chain: str, address: str, limit: int) -> List[Dict]:
        chain_id = _GP_CHAIN_ID.get(chain.lower())
        if not chain_id:
            return []
        url = f"{_GP_BASE}/token_security/{chain_id}"
        data = self._get(url, params={"contract_addresses": address})
        if not data or data.get("code") != 1:
            return []
        result = data.get("result", {})
        info = result.get(address.lower()) or result.get(address) or {}
        holders_raw = info.get("holders") or []
        return [
            {
                "owner": h.get("address", ""),
                "percent": self._sf(h.get("percent", 0)) * 100,
                "balance": self._sf(h.get("balance", 0)),
            }
            for h in holders_raw[:limit]
        ]

    # ------------------------------------------------------------------
    # top_traders  (not available free)
    # ------------------------------------------------------------------
    def top_traders(
        self,
        chain: str,
        address: str,
        limit: int = 10,
        time_frame: str = "24h",
    ) -> List[Dict]:
        """Not available via free APIs. Returns empty list; scorer handles gracefully."""
        return []

    # ------------------------------------------------------------------
    # wallet_pnl
    # ------------------------------------------------------------------
    def wallet_pnl(
        self, chain: str, wallet: str, duration: str = "7d"
    ) -> Dict:
        """
        Return wallet PnL summary.
        Keys: realized_profit, unrealized_profit, win_rate, total_trades
        Helius Solana only; other chains return zero-filled dict.
        """
        empty = {
            "realized_profit": 0.0,
            "unrealized_profit": 0.0,
            "win_rate": 0.0,
            "total_trades": 0,
        }
        if chain.lower() != "solana" or not self.api_key:
            return empty

        url = f"{_HELIUS_API}/addresses/{wallet}/transactions"
        data = self._get(url, params={"api-key": self.api_key, "type": "SWAP", "limit": 100})
        if not data or not isinstance(data, list):
            return empty

        wins = 0
        total = 0
        realized = 0.0
        for tx in data:
            swap = tx.get("events", {}).get("swap", {})
            if not swap:
                continue
            total += 1
            out_val = sum(
                self._sf(t.get("tokenAmount", 0))
                for t in (swap.get("tokenOutputs") or [])
            )
            in_val = sum(
                self._sf(t.get("tokenAmount", 0))
                for t in (swap.get("tokenInputs") or [])
            )
            pnl = out_val - in_val
            realized += pnl
            if pnl > 0:
                wins += 1

        return {
            "realized_profit": realized,
            "unrealized_profit": 0.0,
            "win_rate": (wins / total * 100) if total > 0 else 0.0,
            "total_trades": total,
        }



def normalize_list(data: Any, nested_keys: Sequence[str]) -> List[Dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if not isinstance(data, dict):
        return []
    for key in nested_keys:
        value = data.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = normalize_list(value, nested_keys)
            if nested:
                return nested
    return []


class QuantStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.init_schema()

    def close(self) -> None:
        self.conn.close()

    def init_schema(self) -> None:
        self.conn.executescript(
            """
            PRAGMA journal_mode=WAL;

            CREATE TABLE IF NOT EXISTS tokens (
                chain TEXT NOT NULL,
                address TEXT NOT NULL,
                symbol TEXT,
                name TEXT,
                first_seen_ts TEXT NOT NULL,
                last_seen_ts TEXT NOT NULL,
                PRIMARY KEY (chain, address)
            );

            CREATE TABLE IF NOT EXISTS token_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                chain TEXT NOT NULL,
                address TEXT NOT NULL,
                symbol TEXT,
                name TEXT,
                source TEXT,
                price REAL DEFAULT 0,
                liquidity_usd REAL DEFAULT 0,
                market_cap REAL DEFAULT 0,
                volume_5m_usd REAL DEFAULT 0,
                volume_1h_usd REAL DEFAULT 0,
                volume_24h_usd REAL DEFAULT 0,
                price_change_5m_pct REAL DEFAULT 0,
                price_change_1h_pct REAL DEFAULT 0,
                price_change_24h_pct REAL DEFAULT 0,
                holder_count INTEGER DEFAULT 0,
                holder_change_24h INTEGER DEFAULT 0,
                top10_holder_pct REAL DEFAULT 0,
                is_mintable INTEGER DEFAULT 0,
                freeze_authority INTEGER DEFAULT 0,
                raw_overview TEXT,
                raw_security TEXT
            );

            CREATE TABLE IF NOT EXISTS trade_aggs (
                snapshot_id INTEGER PRIMARY KEY,
                buy_count INTEGER DEFAULT 0,
                sell_count INTEGER DEFAULT 0,
                buy_volume_usd REAL DEFAULT 0,
                sell_volume_usd REAL DEFAULT 0,
                whale_buy_count INTEGER DEFAULT 0,
                whale_sell_count INTEGER DEFAULT 0,
                whale_buy_volume_usd REAL DEFAULT 0,
                whale_sell_volume_usd REAL DEFAULT 0,
                unique_wallets INTEGER DEFAULT 0,
                largest_trade_usd REAL DEFAULT 0,
                raw_sample TEXT,
                FOREIGN KEY(snapshot_id) REFERENCES token_snapshots(id)
            );

            CREATE TABLE IF NOT EXISTS top_traders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id INTEGER NOT NULL,
                wallet TEXT,
                pnl_usd REAL DEFAULT 0,
                volume_usd REAL DEFAULT 0,
                trade_count INTEGER DEFAULT 0,
                buy_count INTEGER DEFAULT 0,
                sell_count INTEGER DEFAULT 0,
                win_rate REAL DEFAULT 0,
                raw_json TEXT,
                FOREIGN KEY(snapshot_id) REFERENCES token_snapshots(id)
            );

            CREATE TABLE IF NOT EXISTS signals (
                snapshot_id INTEGER PRIMARY KEY,
                ts TEXT NOT NULL,
                chain TEXT NOT NULL,
                address TEXT NOT NULL,
                symbol TEXT,
                pump_score REAL DEFAULT 0,
                dump_score REAL DEFAULT 0,
                anomaly_score REAL DEFAULT 0,
                smart_money_score REAL DEFAULT 0,
                risk_score REAL DEFAULT 0,
                label TEXT,
                reasons_json TEXT,
                FOREIGN KEY(snapshot_id) REFERENCES token_snapshots(id)
            );

            CREATE TABLE IF NOT EXISTS signal_outcomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id INTEGER NOT NULL,
                horizon_min INTEGER NOT NULL,
                target_pct REAL NOT NULL,
                evaluated_ts TEXT NOT NULL,
                chain TEXT NOT NULL,
                address TEXT NOT NULL,
                symbol TEXT,
                label TEXT,
                predicted_direction TEXT NOT NULL,
                entry_price REAL DEFAULT 0,
                current_price REAL DEFAULT 0,
                return_pct REAL DEFAULT 0,
                is_true INTEGER DEFAULT 0,
                reasons_json TEXT,
                UNIQUE(snapshot_id, horizon_min, target_pct),
                FOREIGN KEY(snapshot_id) REFERENCES token_snapshots(id)
            );

            CREATE INDEX IF NOT EXISTS idx_snapshots_token_ts
                ON token_snapshots(chain, address, ts);
            CREATE INDEX IF NOT EXISTS idx_signals_ts
                ON signals(ts);
            CREATE INDEX IF NOT EXISTS idx_signals_scores
                ON signals(pump_score, dump_score, anomaly_score);
            CREATE INDEX IF NOT EXISTS idx_outcomes_eval
                ON signal_outcomes(evaluated_ts, is_true);
            """
        )
        self.conn.commit()

    def upsert_token(self, chain: str, address: str, symbol: str, name: str, ts: str) -> None:
        self.conn.execute(
            """
            INSERT INTO tokens(chain, address, symbol, name, first_seen_ts, last_seen_ts)
            VALUES(?, ?, ?, ?, ?, ?)
            ON CONFLICT(chain, address) DO UPDATE SET
                symbol=excluded.symbol,
                name=excluded.name,
                last_seen_ts=excluded.last_seen_ts
            """,
            (chain, address, symbol, name, ts, ts),
        )

    def insert_snapshot(self, snapshot: Dict[str, Any]) -> int:
        columns = [
            "ts", "chain", "address", "symbol", "name", "source", "price", "liquidity_usd",
            "market_cap", "volume_5m_usd", "volume_1h_usd", "volume_24h_usd",
            "price_change_5m_pct", "price_change_1h_pct", "price_change_24h_pct",
            "holder_count", "holder_change_24h", "top10_holder_pct", "is_mintable",
            "freeze_authority", "raw_overview", "raw_security",
        ]
        values = [snapshot.get(col) for col in columns]
        cur = self.conn.execute(
            f"INSERT INTO token_snapshots({', '.join(columns)}) VALUES({', '.join(['?'] * len(columns))})",
            values,
        )
        return int(cur.lastrowid)

    def insert_trade_agg(self, snapshot_id: int, agg: Dict[str, Any]) -> None:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO trade_aggs(
                snapshot_id, buy_count, sell_count, buy_volume_usd, sell_volume_usd,
                whale_buy_count, whale_sell_count, whale_buy_volume_usd, whale_sell_volume_usd,
                unique_wallets, largest_trade_usd, raw_sample
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot_id,
                agg["buy_count"],
                agg["sell_count"],
                agg["buy_volume_usd"],
                agg["sell_volume_usd"],
                agg["whale_buy_count"],
                agg["whale_sell_count"],
                agg["whale_buy_volume_usd"],
                agg["whale_sell_volume_usd"],
                agg["unique_wallets"],
                agg["largest_trade_usd"],
                json.dumps(agg.get("raw_sample", []), separators=(",", ":")),
            ),
        )

    def insert_top_traders(self, snapshot_id: int, traders: Sequence[Dict[str, Any]]) -> None:
        for trader in traders:
            wallet = str(first_value(trader, ["wallet", "wallet_address", "address", "owner"], "") or "")
            self.conn.execute(
                """
                INSERT INTO top_traders(
                    snapshot_id, wallet, pnl_usd, volume_usd, trade_count,
                    buy_count, sell_count, win_rate, raw_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    wallet,
                    first_float(trader, ["totalPnl", "pnl", "pnl_usd", "realized_pnl",
                                         "realizedPnl", "profit"]),
                    first_float(trader, ["volumeUsd", "volume_usd", "volumeUSD",
                                         "trade_volume", "volume"]),
                    first_int(trader, ["trade", "trade_count", "trades", "total_trades"]),
                    first_int(trader, ["tradeBuy", "buy_count", "buys"]),
                    first_int(trader, ["tradeSell", "sell_count", "sells"]),
                    first_float(trader, ["win_rate", "winRate"]),
                    json.dumps(trader, default=str, separators=(",", ":")),
                ),
            )

    def insert_signal(self, snapshot_id: int, signal: Dict[str, Any]) -> None:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO signals(
                snapshot_id, ts, chain, address, symbol, pump_score, dump_score,
                anomaly_score, smart_money_score, risk_score, label, reasons_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot_id,
                signal["ts"],
                signal["chain"],
                signal["address"],
                signal["symbol"],
                signal["pump_score"],
                signal["dump_score"],
                signal["anomaly_score"],
                signal["smart_money_score"],
                signal["risk_score"],
                signal["label"],
                json.dumps(signal["reasons"], separators=(",", ":")),
            ),
        )

    def latest_previous_snapshot(self, chain: str, address: str, before_id: int) -> Optional[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT * FROM token_snapshots
            WHERE chain=? AND address=? AND id < ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (chain, address, before_id),
        ).fetchone()

    def latest_signal_rows(self, limit: int = 50) -> List[sqlite3.Row]:
        return list(
            self.conn.execute(
                """
                SELECT s.*, sn.price, sn.liquidity_usd, sn.volume_1h_usd,
                       sn.price_change_1h_pct, ta.buy_volume_usd, ta.sell_volume_usd,
                       ta.whale_buy_volume_usd, ta.whale_sell_volume_usd
                FROM signals s
                JOIN token_snapshots sn ON sn.id = s.snapshot_id
                LEFT JOIN trade_aggs ta ON ta.snapshot_id = s.snapshot_id
                ORDER BY s.ts DESC,
                         MAX(s.pump_score, s.dump_score, s.anomaly_score) DESC
                LIMIT ?
                """,
                (limit,),
            )
        )

    def pending_outcome_rows(
        self,
        horizon_min: int,
        target_pct: float,
        limit: int = 300,
    ) -> List[sqlite3.Row]:
        return list(
            self.conn.execute(
                """
                SELECT s.*, sn.price AS entry_price, sn.ts AS entry_ts
                FROM signals s
                JOIN token_snapshots sn ON sn.id = s.snapshot_id
                WHERE NOT EXISTS (
                    SELECT 1 FROM signal_outcomes o
                    WHERE o.snapshot_id = s.snapshot_id
                      AND o.horizon_min = ?
                      AND o.target_pct = ?
                )
                ORDER BY s.ts DESC
                LIMIT ?
                """,
                (horizon_min, target_pct, limit),
            )
        )

    def insert_outcome(self, outcome: Dict[str, Any]) -> None:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO signal_outcomes(
                snapshot_id, horizon_min, target_pct, evaluated_ts, chain, address,
                symbol, label, predicted_direction, entry_price, current_price,
                return_pct, is_true, reasons_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                outcome["snapshot_id"],
                outcome["horizon_min"],
                outcome["target_pct"],
                outcome["evaluated_ts"],
                outcome["chain"],
                outcome["address"],
                outcome["symbol"],
                outcome["label"],
                outcome["predicted_direction"],
                outcome["entry_price"],
                outcome["current_price"],
                outcome["return_pct"],
                1 if outcome["is_true"] else 0,
                json.dumps(outcome.get("reasons", []), separators=(",", ":")),
            ),
        )

    def latest_outcome_rows(self, limit: int = 50) -> List[sqlite3.Row]:
        return list(
            self.conn.execute(
                """
                SELECT *
                FROM signal_outcomes
                ORDER BY evaluated_ts DESC
                LIMIT ?
                """,
                (limit,),
            )
        )

    def commit(self) -> None:
        self.conn.commit()


@dataclass
class ScanResult:
    snapshot_ids: List[int]
    signals: List[Dict[str, Any]]
    errors: List[str]
    metadata: Dict[str, Any]


class FeatureBuilder:
    def __init__(self, whale_threshold_usd: float = 10_000.0):
        self.whale_threshold_usd = whale_threshold_usd

    def token_address(self, token: Dict[str, Any]) -> str:
        return str(first_value(token, ["address", "token_address", "mint", "contractAddress"], "") or "")

    def snapshot_from_payload(
        self,
        ts: str,
        chain: str,
        source: str,
        token_seed: Dict[str, Any],
        overview: Dict[str, Any],
        security: Dict[str, Any],
    ) -> Dict[str, Any]:
        address = self.token_address(overview) or self.token_address(token_seed)
        symbol = str(first_value(overview, ["symbol", "token_symbol"], first_value(token_seed, ["symbol"], "")) or "")
        name = str(first_value(overview, ["name", "token_name"], first_value(token_seed, ["name"], "")) or "")
        return {
            "ts": ts,
            "chain": chain,
            "address": address,
            "symbol": symbol,
            "name": name,
            "source": source,
            "price": first_float(overview, ["price", "price_usd", "value"]),
            "liquidity_usd": first_float(overview, ["liquidity", "liquidity_usd", "liquidityUSD"]),
            "market_cap": first_float(overview, ["mc", "market_cap", "marketCap", "fdv"]),
            "volume_5m_usd": first_float(overview, ["v5m", "v5mUSD", "volume_5m_usd", "volume5m"]),
            "volume_1h_usd": first_float(overview, ["v1h", "v1hUSD", "volume_1h_usd", "volume1h"]),
            "volume_24h_usd": first_float(overview, ["v24h", "v24hUSD", "volume_24h_usd", "volume24h"]),
            "price_change_5m_pct": first_float(
                overview, ["priceChange5mPercent", "price_change_5m", "price_change_5m_pct"]
            ),
            "price_change_1h_pct": first_float(
                overview, ["priceChange1hPercent", "price_change_1h", "price_change_1h_pct"]
            ),
            "price_change_24h_pct": first_float(
                overview, ["priceChange24hPercent", "price_change_24h", "price_change_24h_pct"]
            ),
            "holder_count": first_int(overview, ["holder", "holders", "holder_count"]),
            "holder_change_24h": first_int(overview, ["holder_change_24h", "holderChange24h"]),
            "top10_holder_pct": first_float(security, ["top_10_holder_percent", "top10HolderPercent", "top10_holder_pct"]),
            "is_mintable": flag_int(first_value(security, ["is_mintable", "mintable"], 0)),
            "freeze_authority": flag_int(first_value(security, ["freeze_authority", "freezeAuthority"], 0)),
            "raw_overview": json.dumps(overview, default=str, separators=(",", ":")),
            "raw_security": json.dumps(security, default=str, separators=(",", ":")),
        }

    def aggregate_trades(self, trades: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        buy_count = sell_count = whale_buy_count = whale_sell_count = 0
        buy_volume = sell_volume = whale_buy_volume = whale_sell_volume = 0.0
        largest = 0.0
        wallets = set()
        normalized_sample = []

        for trade in trades:
            side = str(first_value(trade, ["side", "type", "txType", "tradeType"], "") or "").lower()
            value = first_float(trade, ["value_usd", "volumeUSD", "volume_usd", "amount_usd", "quote_volume"])
            owner = str(first_value(trade, ["owner", "wallet", "trader", "source_owner", "from"], "") or "")
            if owner:
                wallets.add(owner)
            largest = max(largest, value)
            is_buy = "buy" in side
            is_sell = "sell" in side
            if is_buy:
                buy_count += 1
                buy_volume += value
                if value >= self.whale_threshold_usd:
                    whale_buy_count += 1
                    whale_buy_volume += value
            elif is_sell:
                sell_count += 1
                sell_volume += value
                if value >= self.whale_threshold_usd:
                    whale_sell_count += 1
                    whale_sell_volume += value
            if len(normalized_sample) < 20:
                normalized_sample.append({"side": side, "value_usd": value, "owner": owner})

        return {
            "buy_count": buy_count,
            "sell_count": sell_count,
            "buy_volume_usd": buy_volume,
            "sell_volume_usd": sell_volume,
            "whale_buy_count": whale_buy_count,
            "whale_sell_count": whale_sell_count,
            "whale_buy_volume_usd": whale_buy_volume,
            "whale_sell_volume_usd": whale_sell_volume,
            "unique_wallets": len(wallets),
            "largest_trade_usd": largest,
            "raw_sample": normalized_sample,
        }


class SignalScorer:
    def score(
        self,
        snapshot_id: int,
        snapshot: Dict[str, Any],
        trade_agg: Dict[str, Any],
        top_traders: Sequence[Dict[str, Any]],
        previous: Optional[sqlite3.Row],
    ) -> Dict[str, Any]:
        reasons: List[str] = []
        risk_reasons: List[str] = []

        price = to_float(snapshot["price"])
        liquidity = to_float(snapshot["liquidity_usd"])
        v1h = to_float(snapshot["volume_1h_usd"])
        v24h = to_float(snapshot["volume_24h_usd"])
        holder_count = to_int(snapshot["holder_count"])
        holder_change = to_int(snapshot["holder_change_24h"])
        top10_pct = to_float(snapshot["top10_holder_pct"])
        price_1h = to_float(snapshot["price_change_1h_pct"])

        derived_price_change = 0.0
        liquidity_change = 0.0
        if previous:
            derived_price_change = pct_change(price, to_float(previous["price"]))
            liquidity_change = pct_change(liquidity, to_float(previous["liquidity_usd"]))
            if abs(price_1h) < 0.001:
                price_1h = derived_price_change

        hourly_volume_ratio = v1h / (v24h / 24.0) if v24h > 0 else 0.0
        total_trade_volume = trade_agg["buy_volume_usd"] + trade_agg["sell_volume_usd"]
        buy_imbalance = 0.0
        if total_trade_volume > 0:
            buy_imbalance = (trade_agg["buy_volume_usd"] - trade_agg["sell_volume_usd"]) / total_trade_volume
        whale_net = trade_agg["whale_buy_volume_usd"] - trade_agg["whale_sell_volume_usd"]
        whale_abs = trade_agg["whale_buy_volume_usd"] + trade_agg["whale_sell_volume_usd"]
        whale_imbalance = whale_net / whale_abs if whale_abs > 0 else 0.0

        trader_pnl = sum(first_float(t, ["pnl", "pnl_usd", "realized_pnl", "profit"]) for t in top_traders[:10])
        trader_volume = sum(first_float(t, ["volume", "volume_usd", "volumeUSD"]) for t in top_traders[:10])
        positive_trader_count = sum(1 for t in top_traders[:10] if first_float(t, ["pnl", "pnl_usd", "profit"]) > 0)

        risk_score = 0.0
        if snapshot["is_mintable"]:
            risk_score += 25
            risk_reasons.append("mintable")
        if snapshot["freeze_authority"]:
            risk_score += 25
            risk_reasons.append("freeze_authority")
        if top10_pct > 50:
            risk_score += 25
            risk_reasons.append(f"top10_holder_pct>{top10_pct:.1f}")
        if top10_pct > 80:
            risk_score += 15
            risk_reasons.append("extreme_holder_concentration")
        if liquidity and liquidity < 2_000:
            risk_score += 12
            risk_reasons.append("thin_liquidity")
        if holder_count and holder_count < 100:
            risk_score += 8
            risk_reasons.append("low_holder_count")
        risk_score = clamp(risk_score)

        pump_score = 0.0
        pump_score += clamp(price_1h, 0, 40) * 0.9
        pump_score += clamp(hourly_volume_ratio * 8, 0, 30)
        pump_score += clamp(buy_imbalance * 35, 0, 25)
        pump_score += clamp(whale_imbalance * 30, 0, 25)
        pump_score += clamp(log1p_pos(max(whale_net, 0)) / 12 * 20, 0, 20)
        pump_score += clamp(holder_change / 25, 0, 15)
        pump_score += clamp(positive_trader_count * 3, 0, 15)
        pump_score -= risk_score * 0.35

        dump_score = 0.0
        dump_score += clamp(-price_1h, 0, 40) * 0.9
        dump_score += clamp(-buy_imbalance * 35, 0, 25)
        dump_score += clamp(-whale_imbalance * 30, 0, 25)
        dump_score += clamp(log1p_pos(max(-whale_net, 0)) / 12 * 20, 0, 20)
        dump_score += clamp(-liquidity_change, 0, 35) * 0.7
        dump_score += clamp(-holder_change / 25, 0, 15)
        dump_score += risk_score * 0.25

        smart_money_score = 0.0
        smart_money_score += clamp(log1p_pos(max(trader_pnl, 0)) / 12 * 40, 0, 40)
        smart_money_score += clamp(log1p_pos(max(trader_volume, 0)) / 14 * 30, 0, 30)
        smart_money_score += clamp(positive_trader_count * 4, 0, 30)
        smart_money_score += clamp(buy_imbalance * 20, 0, 15)
        smart_money_score = clamp(smart_money_score - risk_score * 0.2)

        anomaly_score = self._fallback_anomaly_score(
            price_1h=price_1h,
            hourly_volume_ratio=hourly_volume_ratio,
            buy_imbalance=buy_imbalance,
            whale_net=whale_net,
            liquidity_change=liquidity_change,
        )

        if price_1h >= 12 and hourly_volume_ratio >= 3:
            reasons.append("sudden_rise_price_plus_volume")
        if whale_net >= 10_000 and whale_imbalance > 0.25:
            reasons.append("whale_accumulation")
        if buy_imbalance > 0.35:
            reasons.append("buy_pressure")
        if smart_money_score >= 55:
            reasons.append("smart_money_pressure")
        if price_1h <= -12 and buy_imbalance < -0.25:
            reasons.append("selloff_distribution")
        if whale_net <= -10_000 and whale_imbalance < -0.25:
            reasons.append("whale_distribution")
        if liquidity_change <= -20:
            reasons.append("liquidity_drop")
        if risk_reasons:
            reasons.extend([f"risk:{r}" for r in risk_reasons])
        if not reasons:
            reasons.append("normal_watch")

        pump_score = clamp(pump_score)
        dump_score = clamp(dump_score)
        anomaly_score = clamp(anomaly_score)
        smart_money_score = clamp(smart_money_score)

        label = "watch"
        if risk_score >= 65 and max(pump_score, smart_money_score) < 85:
            label = "avoid_high_risk"
        elif dump_score >= 65 and dump_score > pump_score:
            label = "dump_risk"
        elif pump_score >= 70 and smart_money_score >= 45 and risk_score < 60:
            label = "pump_candidate"
        elif anomaly_score >= 70:
            label = "anomaly_watch"
        elif whale_net >= 10_000 and buy_imbalance > 0.2:
            label = "whale_accumulation"

        return {
            "snapshot_id": snapshot_id,
            "ts": snapshot["ts"],
            "chain": snapshot["chain"],
            "address": snapshot["address"],
            "symbol": snapshot["symbol"],
            "binance_usdt_futures": bool(snapshot.get("binance_usdt_futures")),
            "binance_symbol": snapshot.get("binance_symbol", ""),
            "binance_base_asset": snapshot.get("binance_base_asset", ""),
            "binance_match_type": snapshot.get("binance_match_type", ""),
            "pump_score": round(pump_score, 2),
            "dump_score": round(dump_score, 2),
            "anomaly_score": round(anomaly_score, 2),
            "smart_money_score": round(smart_money_score, 2),
            "risk_score": round(risk_score, 2),
            "label": label,
            "reasons": reasons,
            "metrics": {
                "price": price,
                "liquidity_usd": liquidity,
                "price_change_1h_pct": price_1h,
                "derived_price_change_pct": derived_price_change,
                "volume_1h_usd": v1h,
                "hourly_volume_ratio": hourly_volume_ratio,
                "buy_imbalance": buy_imbalance,
                "whale_net_usd": whale_net,
                "liquidity_change_pct": liquidity_change,
                "top_trader_pnl_usd": trader_pnl,
            },
        }

    def _fallback_anomaly_score(
        self,
        price_1h: float,
        hourly_volume_ratio: float,
        buy_imbalance: float,
        whale_net: float,
        liquidity_change: float,
    ) -> float:
        score = 0.0
        score += clamp(abs(price_1h) * 1.4, 0, 35)
        score += clamp(hourly_volume_ratio * 9, 0, 30)
        score += clamp(abs(buy_imbalance) * 25, 0, 20)
        score += clamp(log1p_pos(abs(whale_net)) / 12 * 20, 0, 20)
        score += clamp(abs(liquidity_change) * 0.7, 0, 15)
        return score


class CrossSectionalML:
    """
    Optional unsupervised anomaly layer.

    If scikit-learn is installed, IsolationForest is used on the current scan
    batch. Otherwise the heuristic anomaly score remains active.
    """

    def maybe_apply(self, signals: List[Dict[str, Any]]) -> None:
        if len(signals) < 20:
            return
        try:
            from sklearn.ensemble import IsolationForest  # type: ignore
        except Exception:
            return

        matrix = []
        for signal in signals:
            m = signal.get("metrics", {})
            matrix.append(
                [
                    to_float(m.get("price_change_1h_pct")),
                    log1p_pos(to_float(m.get("volume_1h_usd"))),
                    to_float(m.get("hourly_volume_ratio")),
                    to_float(m.get("buy_imbalance")),
                    log1p_pos(abs(to_float(m.get("whale_net_usd")))),
                    to_float(m.get("liquidity_change_pct")),
                    to_float(signal.get("risk_score")),
                ]
            )

        try:
            model = IsolationForest(n_estimators=100, contamination=0.08, random_state=42)
            model.fit(matrix)
            raw = model.score_samples(matrix)
        except Exception:
            return

        min_raw = min(raw)
        max_raw = max(raw)
        spread = max(max_raw - min_raw, 1e-9)
        for signal, raw_score in zip(signals, raw):
            iso_score = (max_raw - raw_score) / spread * 100.0
            signal["anomaly_score"] = round(max(to_float(signal["anomaly_score"]), iso_score), 2)
            if signal["anomaly_score"] >= 70 and signal["label"] == "watch":
                signal["label"] = "anomaly_watch"
            if signal["anomaly_score"] >= 70:
                signal["reasons"].append("ml_isolation_forest_anomaly")


class LiveScanner:
    def __init__(
        self,
        client: AzalystClient,
        store: QuantStore,
        whale_threshold_usd: float = 10_000.0,
        include_new_listings: bool = True,
        binance_usdt_only: bool = False,
        binance_universe: Optional[BinanceFuturesUniverse] = None,
        binance_min_liquidity_usd: float = 5_000.0,
    ):
        self.client = client
        self.store = store
        self.features = FeatureBuilder(whale_threshold_usd=whale_threshold_usd)
        self.scorer = SignalScorer()
        self.ml = CrossSectionalML()
        self.include_new_listings = include_new_listings
        self.binance_usdt_only = binance_usdt_only
        self.binance_universe = binance_universe
        self.binance_min_liquidity_usd = binance_min_liquidity_usd

    def scan(
        self,
        chains: Sequence[str],
        limit: int = 50,
        trade_limit: int = 100,
        top_trader_limit: int = 10,
    ) -> ScanResult:
        ts = utc_now()
        snapshot_ids: List[int] = []
        signals: List[Dict[str, Any]] = []
        errors: List[str] = []
        metadata = {
            "scan_chains": list(chains),
            "trade_limit": int(trade_limit),
            "top_trader_limit": int(top_trader_limit),
            "smart_money_enabled": bool(trade_limit > 0 and top_trader_limit > 0),
            "binance_usdt_only": bool(self.binance_usdt_only),
            "binance_symbol_count": 0,
            "binance_min_liquidity_usd": self.binance_min_liquidity_usd,
            "binance_source": "disabled",
        }

        if self.binance_usdt_only:
            if self.binance_universe is None:
                self.binance_universe = BinanceFuturesUniverse(timeout=max(self.client.timeout, 15))
            try:
                metadata["binance_symbol_count"] = len(self.binance_universe.refresh())
                metadata["binance_source"] = self.binance_universe.last_source
            except Exception as exc:
                errors.append(f"binance futures universe fetch error: {exc}")
                return ScanResult(snapshot_ids=snapshot_ids, signals=signals, errors=errors, metadata=metadata)

        for chain in chains:
            universe = self._discover_universe(chain, limit, errors)
            for token_seed, source in universe:
                address = self.features.token_address(token_seed)
                if not address:
                    continue
                try:
                    overview = self.client.token_overview(chain, address)
                    if "error" in overview:
                        errors.append(f"{chain}:{address}: overview error {overview.get('error')}")
                        continue
                    security = self.client.token_security(chain, address)
                    if "error" in security:
                        security = {}
                    snapshot = self.features.snapshot_from_payload(ts, chain, source, token_seed, overview, security)
                    if not snapshot["address"]:
                        continue
                    if self.binance_usdt_only:
                        match = self.binance_universe.match_token(snapshot["symbol"]) if self.binance_universe else None
                        if not match:
                            continue
                        if to_float(snapshot["liquidity_usd"]) < self.binance_min_liquidity_usd:
                            continue
                        snapshot.update(match)

                    self.store.upsert_token(chain, snapshot["address"], snapshot["symbol"], snapshot["name"], ts)
                    snapshot_id = self.store.insert_snapshot(snapshot)
                    trades = self.client.token_trades(chain, snapshot["address"], limit=trade_limit)
                    trade_agg = self.features.aggregate_trades(trades)
                    self.store.insert_trade_agg(snapshot_id, trade_agg)

                    top_traders = []
                    if top_trader_limit > 0:
                        top_traders = self.client.top_traders(chain, snapshot["address"], limit=top_trader_limit)
                        self.store.insert_top_traders(snapshot_id, top_traders)

                    previous = self.store.latest_previous_snapshot(chain, snapshot["address"], snapshot_id)
                    signal = self.scorer.score(snapshot_id, snapshot, trade_agg, top_traders, previous)
                    signals.append(signal)
                    snapshot_ids.append(snapshot_id)
                except Exception as exc:
                    errors.append(f"{chain}:{address}: {exc}")

        self.ml.maybe_apply(signals)
        for signal in signals:
            self.store.insert_signal(signal["snapshot_id"], signal)
        self.store.commit()
        metadata["matched_signal_count"] = len(signals)
        return ScanResult(snapshot_ids=snapshot_ids, signals=signals, errors=errors, metadata=metadata)

    def _discover_universe(
        self,
        chain: str,
        limit: int,
        errors: List[str],
    ) -> List[Tuple[Dict[str, Any], str]]:
        seen = set()
        out: List[Tuple[Dict[str, Any], str]] = []

        def add_many(tokens: Iterable[Dict[str, Any]], source: str) -> None:
            for token in tokens:
                address = self.features.token_address(token)
                if not address or address in seen:
                    continue
                if self.binance_usdt_only and self.binance_universe is not None:
                    seed_symbol = str(first_value(token, ["symbol", "token_symbol"], "") or "")
                    if seed_symbol and not self.binance_universe.match_token(seed_symbol):
                        continue
                seen.add(address)
                out.append((token, source))

        if self.binance_usdt_only:
            liquid = self.client.token_list(
                chain,
                limit=max(limit, 25),
                sort_by="liquidity",
                min_liquidity=self.binance_min_liquidity_usd,
            )
            if liquid and "error" in liquid[0]:
                errors.append(f"{chain}: token list liquidity error {liquid[0]}")
            else:
                add_many(liquid, "token_list_liquidity")

            volume = self.client.token_list(
                chain,
                limit=max(limit, 25),
                sort_by="v24hUSD",
                min_liquidity=self.binance_min_liquidity_usd,
            )
            if volume and "error" in volume[0]:
                errors.append(f"{chain}: token list volume error {volume[0]}")
            else:
                add_many(volume, "token_list_volume")

            return out[: max(limit * 2, 25)]

        trending = self.client.token_trending(chain, limit=limit)
        if trending and "error" in trending[0]:
            errors.append(f"{chain}: trending error {trending[0]}")
        else:
            add_many(trending, "trending")

        if self.include_new_listings:
            listings = self.client.new_listings(chain, limit=max(10, limit // 2))
            if listings and "error" in listings[0]:
                errors.append(f"{chain}: new listing error {listings[0]}")
            else:
                add_many(listings, "new_listing")

        return out[: limit + max(10, limit // 2)]


class OutcomeEvaluator:
    def __init__(self, client: AzalystClient, store: QuantStore):
        self.client = client
        self.store = store

    def evaluate(
        self,
        horizon_min: int = 60,
        target_pct: float = 10.0,
        max_candidates: int = 300,
    ) -> List[Dict[str, Any]]:
        now = datetime.now(timezone.utc)
        outcomes: List[Dict[str, Any]] = []
        rows = self.store.pending_outcome_rows(
            horizon_min=horizon_min,
            target_pct=target_pct,
            limit=max_candidates,
        )

        for row in rows:
            row_dict = dict(row)
            entry_ts = parse_utc(row_dict["entry_ts"])
            age_min = (now - entry_ts).total_seconds() / 60.0
            if age_min < horizon_min:
                continue

            direction = self._direction(row_dict)
            if not direction:
                continue

            overview = self.client.token_overview(row_dict["chain"], row_dict["address"])
            if "error" in overview:
                continue

            current_price = first_float(overview, ["price", "price_usd", "value"])
            entry_price = to_float(row_dict["entry_price"])
            if entry_price <= 0 or current_price <= 0:
                continue

            ret = pct_change(current_price, entry_price)
            is_true = ret >= target_pct if direction == "up" else ret <= -target_pct
            reasons = self._outcome_reasons(row_dict, direction, ret, target_pct)
            outcome = {
                "snapshot_id": row_dict["snapshot_id"],
                "horizon_min": horizon_min,
                "target_pct": target_pct,
                "evaluated_ts": utc_now(),
                "chain": row_dict["chain"],
                "address": row_dict["address"],
                "symbol": row_dict.get("symbol") or "",
                "label": row_dict.get("label") or "",
                "predicted_direction": direction,
                "entry_price": entry_price,
                "current_price": current_price,
                "return_pct": round(ret, 4),
                "is_true": bool(is_true),
                "reasons": reasons,
            }
            self.store.insert_outcome(outcome)
            outcomes.append(outcome)

        self.store.commit()
        return outcomes

    def _direction(self, signal: Dict[str, Any]) -> Optional[str]:
        label = signal.get("label") or ""
        pump = to_float(signal.get("pump_score"))
        dump = to_float(signal.get("dump_score"))
        if label == "dump_risk":
            return "down"
        if label == "avoid_high_risk" and dump >= pump:
            return "down"
        if label in {"pump_candidate", "whale_accumulation"}:
            return "up"
        if pump >= 55 and pump >= dump:
            return "up"
        if dump >= 55 and dump > pump:
            return "down"
        if label == "anomaly_watch":
            return "up" if pump >= dump else "down"
        return None

    def _outcome_reasons(
        self,
        signal: Dict[str, Any],
        direction: str,
        ret: float,
        target_pct: float,
    ) -> List[str]:
        reasons = [
            f"predicted_{direction}",
            f"return_{ret:.2f}pct",
            f"target_{target_pct:.2f}pct",
            f"label_{signal.get('label')}",
        ]
        if direction == "up" and ret >= target_pct:
            reasons.append("pump_confirmed")
        elif direction == "down" and ret <= -target_pct:
            reasons.append("dump_confirmed")
        else:
            reasons.append("not_confirmed")
        return reasons


def sorted_signals(signals: Sequence[Dict[str, Any]], limit: int = 25) -> List[Dict[str, Any]]:
    return sorted(
        signals,
        key=lambda s: max(
            to_float(s.get("pump_score")),
            to_float(s.get("dump_score")),
            to_float(s.get("anomaly_score")),
            to_float(s.get("smart_money_score")),
        ),
        reverse=True,
    )[:limit]


def print_signal_table(signals: Sequence[Dict[str, Any]], limit: int = 25) -> None:
    rows = sorted_signals(signals, limit)
    if not rows:
        print("No signals found.")
        return
    print(f"{'CHAIN':10} {'SYMBOL':12} {'LABEL':20} {'PUMP':>6} {'DUMP':>6} {'ANOM':>6} {'SMART':>6} {'RISK':>6}  REASONS")
    print("-" * 120)
    for signal in rows:
        reasons = ", ".join(signal.get("reasons", [])[:4])
        print(console_safe(
            f"{signal['chain'][:10]:10} {str(signal.get('symbol') or '?')[:12]:12} "
            f"{signal['label'][:20]:20} {signal['pump_score']:6.1f} {signal['dump_score']:6.1f} "
            f"{signal['anomaly_score']:6.1f} {signal['smart_money_score']:6.1f} {signal['risk_score']:6.1f}  "
            f"{reasons}"
        ))


def print_outcome_table(outcomes: Sequence[Dict[str, Any]], limit: int = 25) -> None:
    rows = list(outcomes)[:limit]
    if not rows:
        print("No mature signals to evaluate yet.")
        return
    print(f"{'CHAIN':10} {'SYMBOL':12} {'LABEL':20} {'DIR':>5} {'RET%':>8} {'TRUE':>5}  REASONS")
    print("-" * 92)
    for outcome in rows:
        reasons = ", ".join(outcome.get("reasons", [])[:4])
        print(console_safe(
            f"{outcome['chain'][:10]:10} {str(outcome.get('symbol') or '?')[:12]:12} "
            f"{outcome['label'][:20]:20} {outcome['predicted_direction']:>5} "
            f"{outcome['return_pct']:8.2f} {str(bool(outcome['is_true'])):>5}  {reasons}"
        ))


def write_reports(report_dir: Path, result: ScanResult, prefix: str = "quant_signals") -> Tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = report_dir / f"{prefix}_{stamp}.json"
    csv_path = report_dir / f"{prefix}_{stamp}.csv"

    payload = {
        "kind": "quant_signals",
        "generated_at": utc_now(),
        "snapshot_count": len(result.snapshot_ids),
        "errors": result.errors,
        "filters": result.metadata,
        "signals": sorted_signals(result.signals, limit=len(result.signals)),
    }
    json_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    (report_dir / "latest_quant_signals.json").write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8",
    )

    fieldnames = [
        "ts", "chain", "address", "symbol", "binance_symbol", "binance_base_asset",
        "binance_match_type", "label", "pump_score", "dump_score",
        "anomaly_score", "smart_money_score", "risk_score", "reasons",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for signal in payload["signals"]:
            writer.writerow(
                {
                    "ts": signal["ts"],
                    "chain": signal["chain"],
                    "address": signal["address"],
                    "symbol": signal["symbol"],
                    "binance_symbol": signal.get("binance_symbol", ""),
                    "binance_base_asset": signal.get("binance_base_asset", ""),
                    "binance_match_type": signal.get("binance_match_type", ""),
                    "label": signal["label"],
                    "pump_score": signal["pump_score"],
                    "dump_score": signal["dump_score"],
                    "anomaly_score": signal["anomaly_score"],
                    "smart_money_score": signal["smart_money_score"],
                    "risk_score": signal["risk_score"],
                    "reasons": ";".join(signal.get("reasons", [])),
                }
            )
    latest_csv_path = report_dir / "latest_quant_signals.csv"
    latest_csv_path.write_text(csv_path.read_text(encoding="utf-8"), encoding="utf-8")
    return json_path, csv_path


def write_outcome_reports(
    report_dir: Path,
    outcomes: Sequence[Dict[str, Any]],
    prefix: str = "quant_outcomes",
) -> Tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = report_dir / f"{prefix}_{stamp}.json"
    csv_path = report_dir / f"{prefix}_{stamp}.csv"
    total = len(outcomes)
    hits = sum(1 for o in outcomes if o.get("is_true"))
    payload = {
        "kind": "quant_outcomes",
        "generated_at": utc_now(),
        "evaluated_count": total,
        "hit_count": hits,
        "hit_rate": round(hits / total, 4) if total else None,
        "outcomes": list(outcomes),
    }
    text = json.dumps(payload, indent=2, default=str)
    json_path.write_text(text, encoding="utf-8")
    (report_dir / "latest_quant_outcomes.json").write_text(text, encoding="utf-8")

    fieldnames = [
        "evaluated_ts", "chain", "address", "symbol", "label", "predicted_direction",
        "entry_price", "current_price", "return_pct", "target_pct", "horizon_min",
        "is_true", "reasons",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for outcome in outcomes:
            writer.writerow(
                {
                    **{k: outcome.get(k, "") for k in fieldnames if k != "reasons"},
                    "reasons": ";".join(outcome.get("reasons", [])),
                }
            )
    (report_dir / "latest_quant_outcomes.csv").write_text(
        csv_path.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    return json_path, csv_path


def write_qwen_brief(
    report_dir: Path,
    signals: Sequence[Dict[str, Any]],
    outcomes: Sequence[Dict[str, Any]] = (),
) -> Optional[Path]:
    api_key = os.getenv("NIM_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI
    except Exception:
        return None

    top_signals = sorted_signals(signals, limit=12)
    hit_count = sum(1 for o in outcomes if o.get("is_true"))
    outcome_summary = {
        "evaluated_count": len(outcomes),
        "hit_count": hit_count,
        "hit_rate": round(hit_count / len(outcomes), 4) if outcomes else None,
    }
    prompt = {
        "task": "Write a concise quant analyst brief for these Azalyst Alpha Scanner token signals. "
                "Do not give financial advice. Be conservative and score-calibrated. "
                "Only call something a strong long if pump_score >= 70 and smart_money_score >= 45. "
                "Only call something a strong short if dump_score >= 65. "
                "Only call something an anomaly if anomaly_score >= 70. "
                "If a name is below those thresholds, describe it as a low-conviction or tentative watch. "
                "Identify the biggest risks, false-positive risk, and what needs confirmation next.",
        "top_signals": top_signals,
        "outcome_summary": outcome_summary,
    }
    try:
        client = OpenAI(
            api_key=api_key,
            base_url=os.getenv("NIM_BASE_URL", "https://integrate.api.nvidia.com/v1"),
        )
        
        models = [
            os.getenv("NIM_PRIMARY_MODEL", "deepseek-ai/deepseek-v4-pro"),
            os.getenv("NIM_FALLBACK_MODEL", "qwen/qwen2.5-coder-32b-instruct")
        ]
        
        brief = None
        for model in models:
            try:
                print(f"  Generating brief with {model}...")
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "You are a cautious quant research analyst."},
                        {"role": "user", "content": json.dumps(prompt, default=str)},
                    ],
                    temperature=0.2,
                    max_tokens=900,
                )
                brief = response.choices[0].message.content or ""
                break
            except Exception as e:
                print(f"  Error with {model}: {e}")
                if model == models[-1]:
                    brief = f"AI brief unavailable: {e}"
                else:
                    print("  Retrying with fallback model...")
        
    except Exception as exc:
        brief = f"AI brief unavailable: {exc}"

    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = report_dir / f"quant_brief_{stamp}.md"
    content = f"# Quant Signal Brief\n\nGenerated: {utc_now()}\n\n{brief}\n"
    path.write_text(content, encoding="utf-8")
    (report_dir / "latest_quant_brief.md").write_text(content, encoding="utf-8")
    return path


def run_scan(args: argparse.Namespace) -> int:
    chains = parse_chains(args.chains)
    client = AzalystClient(api_key=args.api_key, min_delay=args.min_delay)
    store = QuantStore(Path(args.db))
    try:
        scanner = LiveScanner(
            client,
            store,
            whale_threshold_usd=args.whale_threshold,
            include_new_listings=not args.no_new_listings,
            binance_usdt_only=args.binance_usdt_only,
            binance_universe=BinanceFuturesUniverse(timeout=max(client.timeout, 15)) if args.binance_usdt_only else None,
            binance_min_liquidity_usd=args.binance_min_liquidity_usd,
        )
        result = scanner.scan(
            chains=chains,
            limit=args.limit,
            trade_limit=args.trade_limit,
            top_trader_limit=args.top_trader_limit,
        )
        print_signal_table(result.signals, limit=args.show)
        json_path, csv_path = write_reports(Path(args.report_dir), result)
        outcome_paths: Optional[Tuple[Path, Path]] = None
        outcomes: List[Dict[str, Any]] = []
        if getattr(args, "evaluate", False):
            outcomes = OutcomeEvaluator(client, store).evaluate(
                horizon_min=args.outcome_horizon_min,
                target_pct=args.outcome_target_pct,
                max_candidates=args.outcome_max_candidates,
            )
            print()
            print_outcome_table(outcomes, limit=args.show)
            outcome_paths = write_outcome_reports(Path(args.report_dir), outcomes)
        brief_path = None
        if getattr(args, "qwen_brief", False):
            brief_path = write_qwen_brief(Path(args.report_dir), result.signals, outcomes)
        print()
        print(f"Recorded snapshots : {len(result.snapshot_ids)}")
        print(f"Signals JSON       : {json_path}")
        print(f"Signals CSV        : {csv_path}")
        if outcome_paths:
            print(f"Outcomes JSON      : {outcome_paths[0]}")
            print(f"Outcomes CSV       : {outcome_paths[1]}")
        if brief_path:
            print(f"Qwen brief         : {brief_path}")
        if result.errors:
            print(f"Warnings/errors    : {len(result.errors)}")
            for error in result.errors[:8]:
                print(f"  - {error}")
        return 0
    finally:
        store.close()


def run_loop(args: argparse.Namespace) -> int:
    while True:
        started = time.time()
        print(f"\n[{utc_now()}] starting scan")
        code = run_scan(args)
        if code != 0:
            return code
        elapsed = time.time() - started
        sleep_for = max(args.interval - elapsed, 5)
        print(f"[{utc_now()}] next scan in {sleep_for:.0f}s")
        time.sleep(sleep_for)


def run_signals(args: argparse.Namespace) -> int:
    store = QuantStore(Path(args.db))
    try:
        rows = store.latest_signal_rows(limit=args.show)
        signals = []
        for row in rows:
            signal = dict(row)
            try:
                signal["reasons"] = json.loads(signal.pop("reasons_json") or "[]")
            except json.JSONDecodeError:
                signal["reasons"] = []
            signals.append(signal)
        print_signal_table(signals, limit=args.show)
        return 0
    finally:
        store.close()


def run_evaluate(args: argparse.Namespace) -> int:
    client = AzalystClient(api_key=args.api_key, min_delay=args.min_delay)
    store = QuantStore(Path(args.db))
    try:
        outcomes = OutcomeEvaluator(client, store).evaluate(
            horizon_min=args.horizon_min,
            target_pct=args.target_pct,
            max_candidates=args.max_candidates,
        )
        print_outcome_table(outcomes, limit=args.show)
        json_path, csv_path = write_outcome_reports(Path(args.report_dir), outcomes)
        print()
        print(f"Evaluated outcomes : {len(outcomes)}")
        print(f"Outcomes JSON      : {json_path}")
        print(f"Outcomes CSV       : {csv_path}")
        return 0
    finally:
        store.close()


def run_outcomes(args: argparse.Namespace) -> int:
    store = QuantStore(Path(args.db))
    try:
        rows = store.latest_outcome_rows(limit=args.show)
        outcomes = []
        for row in rows:
            outcome = dict(row)
            outcome["is_true"] = bool(outcome.get("is_true"))
            try:
                outcome["reasons"] = json.loads(outcome.pop("reasons_json") or "[]")
            except json.JSONDecodeError:
                outcome["reasons"] = []
            outcomes.append(outcome)
        print_outcome_table(outcomes, limit=args.show)
        return 0
    finally:
        store.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Azalyst Alpha Scanner — live quant scanner and ML signal engine")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--db", default=str(DEFAULT_DB), help="SQLite database path")
        p.add_argument("--api-key", default=os.getenv("HELIUS_API_KEY"), help="Birdeye API key")
        p.add_argument("--chains", default="all", help="Comma-separated chains or 'all'")
        p.add_argument("--limit", type=int, default=40, help="Token universe size per chain")
        p.add_argument("--trade-limit", type=int, default=100, help="Recent token trades to aggregate")
        p.add_argument("--top-trader-limit", type=int, default=8, help="Top traders per token, 0 disables")
        p.add_argument("--whale-threshold", type=float, default=10_000.0, help="Large trade threshold in USD")
        p.add_argument("--min-delay", type=float, default=0.12, help="Minimum seconds between API calls")
        p.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR), help="Report output directory")
        p.add_argument("--show", type=int, default=25, help="Rows to print")
        p.add_argument("--no-new-listings", action="store_true", help="Skip new listings endpoint")
        p.add_argument("--evaluate", action="store_true", help="Evaluate mature stored signals after scanning")
        p.add_argument("--outcome-horizon-min", type=int, default=60, help="Outcome horizon for --evaluate")
        p.add_argument("--outcome-target-pct", type=float, default=10.0, help="Return target for true/false outcomes")
        p.add_argument("--outcome-max-candidates", type=int, default=300, help="Max stored signals to evaluate")
        p.add_argument("--qwen-brief", action="store_true", help="Write an optional Qwen analyst brief when NIM_API_KEY is set")
        p.add_argument("--binance-usdt-only", action="store_true", help="Keep only tokens that match Binance USDT futures symbols")
        p.add_argument("--binance-min-liquidity-usd", type=float, default=5000.0, help="Drop Binance-matched tokens below this on-chain liquidity")

    scan = sub.add_parser("scan", help="Run one live scan and record snapshots")
    add_common(scan)
    scan.set_defaults(func=run_scan)

    loop = sub.add_parser("loop", help="Run live scans forever")
    add_common(loop)
    loop.add_argument("--interval", type=int, default=300, help="Seconds between scan starts")
    loop.set_defaults(func=run_loop)

    signals = sub.add_parser("signals", help="Show latest stored signals")
    signals.add_argument("--db", default=str(DEFAULT_DB), help="SQLite database path")
    signals.add_argument("--show", type=int, default=25, help="Rows to print")
    signals.set_defaults(func=run_signals)

    evaluate = sub.add_parser("evaluate", help="Evaluate older signals as true or false")
    evaluate.add_argument("--db", default=str(DEFAULT_DB), help="SQLite database path")
    evaluate.add_argument("--api-key", default=os.getenv("HELIUS_API_KEY"), help="Birdeye API key")
    evaluate.add_argument("--min-delay", type=float, default=0.12, help="Minimum seconds between API calls")
    evaluate.add_argument("--horizon-min", type=int, default=60, help="Minutes after signal to check")
    evaluate.add_argument("--target-pct", type=float, default=10.0, help="Return threshold for true outcome")
    evaluate.add_argument("--max-candidates", type=int, default=300, help="Max unevaluated signals to check")
    evaluate.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR), help="Report output directory")
    evaluate.add_argument("--show", type=int, default=25, help="Rows to print")
    evaluate.set_defaults(func=run_evaluate)

    outcomes = sub.add_parser("outcomes", help="Show latest stored true/false outcomes")
    outcomes.add_argument("--db", default=str(DEFAULT_DB), help="SQLite database path")
    outcomes.add_argument("--show", type=int, default=25, help="Rows to print")
    outcomes.set_defaults(func=run_outcomes)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("Stopped.")
        return 130
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
