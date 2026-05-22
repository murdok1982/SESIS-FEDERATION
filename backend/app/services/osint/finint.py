from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings, get_settings

logger = get_logger(__name__)

@dataclass
class CryptoTransaction:
    tx_hash: str
    address: str
    amount: float
    currency: str
    timestamp: str = ""
    confirmations: int = 0
    risk_score: float = 0.0
    tags: list[str] = field(default_factory=list)

@dataclass
class FinancialProfile:
    entity_name: str
    crypto_addresses: list[str] = field(default_factory=list)
    transactions: list[CryptoTransaction] = field(default_factory=list)
    total_volume: float = 0.0
    risk_indicators: list[str] = field(default_factory=list)
    sanctions_match: bool = False

class FININTModule:
    """Financial Intelligence module for crypto tracking and AML."""

    SANCTIONS_LISTS = [
        "OFAC SDN",
        "UN Sanctions",
        "EU Sanctions",
    ]

    HIGH_RISK_JURISDICTIONS = [
        "mixer", "tumbler", "darknet", "ransomware", "sanctioned",
    ]

    def __init__(self, blockchain_api_key: str = "", etherscan_api_key: str = "") -> None:
        self._blockchain_api_key = blockchain_api_key
        self._etherscan_api_key = etherscan_api_key
        self._monitored_addresses: dict[str, FinancialProfile] = {}

    def monitor_address(self, address: str, entity_name: str = "") -> None:
        if address not in self._monitored_addresses:
            self._monitored_addresses[address] = FinancialProfile(
                entity_name=entity_name or address[:16],
                crypto_addresses=[address],
            )
            logger.info("crypto_address_monitored", address=address)

    async def analyze_address(self, address: str) -> FinancialProfile:
        profile = self._monitored_addresses.get(address, FinancialProfile(entity_name=address[:16]))

        profile.crypto_addresses = list(set(profile.crypto_addresses + [address]))
        profile.transactions = await self._fetch_transactions(address)
        profile.total_volume = sum(t.amount for t in profile.transactions)
        profile.risk_indicators = self._assess_risk(profile.transactions)
        profile.sanctions_match = await self._check_sanctions(address)

        return profile

    async def _fetch_transactions(self, address: str) -> list[CryptoTransaction]:
        transactions = []
        try:
            import httpx
            async with httpx.AsyncClient(timeout=15) as client:
                if self._etherscan_api_key:
                    resp = await client.get(
                        "https://api.etherscan.io/api",
                        params={
                            "module": "account",
                            "action": "txlist",
                            "address": address,
                            "startblock": 0,
                            "endblock": 99999999,
                            "sort": "desc",
                            "apikey": self._etherscan_api_key,
                        },
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get("status") == "1":
                            for tx in data.get("result", [])[:50]:
                                transactions.append(CryptoTransaction(
                                    tx_hash=tx.get("hash", ""),
                                    address=address,
                                    amount=float(tx.get("value", 0)) / 1e18,
                                    currency="ETH",
                                    timestamp=tx.get("timeStamp", ""),
                                    confirmations=int(tx.get("confirmations", 0)),
                                ))
        except Exception as exc:
            logger.warning("etherscan_query_failed", address=address, error=str(exc))
        return transactions

    def _assess_risk(self, transactions: list[CryptoTransaction]) -> list[str]:
        indicators = []
        total_volume = sum(t.amount for t in transactions)
        if total_volume > 1000000:
            indicators.append("high_volume")
        large_txs = [t for t in transactions if t.amount > 100]
        if len(large_txs) > len(transactions) * 0.5 and transactions:
            indicators.append("large_transactions")
        return indicators

    async def _check_sanctions(self, address: str) -> bool:
        address_hash = hashlib.sha256(address.lower().encode()).hexdigest()[:16]
        known_sanctioned = [
            "12tL3", "3F4b2", "bc1q9",
        ]
        return any(address.startswith(prefix) for prefix in known_sanctioned)

    async def track_flow(self, address: str, hops: int = 3) -> dict[str, Any]:
        flow = {"origin": address, "hops": [], "total_addresses": 0}
        current_addresses = {address}
        for hop in range(hops):
            next_addresses = set()
            for addr in current_addresses:
                txs = await self._fetch_transactions(addr)
                for tx in txs:
                    next_addresses.add(tx.tx_hash[:16])
            flow["hops"].append({
                "hop": hop + 1,
                "addresses": list(next_addresses),
                "count": len(next_addresses),
            })
            flow["total_addresses"] += len(next_addresses)
            current_addresses = next_addresses
            if not current_addresses:
                break
        return flow

    def get_monitored_profiles(self) -> list[FinancialProfile]:
        return list(self._monitored_addresses.values())

finint = FININTModule()
