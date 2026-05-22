from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.core.config import settings, get_settings

logger = get_logger(__name__)

class ThreatLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class IoCType(str, Enum):
    IP = "ip"
    DOMAIN = "domain"
    URL = "url"
    EMAIL = "email"
    HASH_MD5 = "hash_md5"
    HASH_SHA1 = "hash_sha1"
    HASH_SHA256 = "hash_sha256"
    FILE_NAME = "file_name"
    REGISTRY_KEY = "registry_key"

@dataclass
class IndicatorOfCompromise:
    value: str
    ioc_type: IoCType
    threat_level: ThreatLevel = ThreatLevel.LOW
    confidence: float = 0.0
    source: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    mitre_techniques: list[str] = field(default_factory=list)
    first_seen: str = ""
    last_seen: str = ""
    false_positives: int = 0

@dataclass
class ThreatReport:
    title: str
    threat_level: ThreatLevel
    iocs: list[IndicatorOfCompromise] = field(default_factory=list)
    ttps: list[str] = field(default_factory=list)
    affected_systems: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    raw_intelligence: str = ""

class CYBINTModule:
    """Cyber Threat Intelligence module with MITRE ATT&CK mapping."""

    MITRE_ATTACK_TECHNIQUES = {
        "T1566": "Phishing",
        "T1059": "Command and Scripting Interpreter",
        "T1071": "Application Layer Protocol",
        "T1048": "Exfiltration Over Alternative Protocol",
        "T1074": "Data Staged",
        "T1005": "Data from Local System",
        "T1560": "Archive Collected Data",
        "T1041": "Exfiltration Over C2 Channel",
        "T1078": "Valid Accounts",
        "T1110": "Brute Force",
        "T1021": "Remote Services",
        "T1053": "Scheduled Task/Job",
        "T1543": "Create or Modify System Process",
        "T1055": "Process Injection",
        "T1036": "Masquerading",
    }

    def __init__(self, misp_url: str = "", misp_key: str = "", otx_key: str = "") -> None:
        self._misp_url = misp_url
        self._misp_key = misp_key
        self._otx_key = otx_key
        self._ioc_database: list[IndicatorOfCompromise] = []

    def extract_iocs(self, text: str) -> list[IndicatorOfCompromise]:
        iocs = []

        ip_pattern = r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
        for ip in re.findall(ip_pattern, text):
            iocs.append(IndicatorOfCompromise(
                value=ip, ioc_type=IoCType.IP, source="extraction",
            ))

        domain_pattern = r'\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}\b'
        for domain in re.findall(domain_pattern, text):
            if not domain.startswith(("www.", "http", "ftp")):
                iocs.append(IndicatorOfCompromise(
                    value=domain, ioc_type=IoCType.DOMAIN, source="extraction",
                ))

        url_pattern = r'https?://[^\s<>"\']+|www\.[^\s<>"\']+'
        for url in re.findall(url_pattern, text):
            iocs.append(IndicatorOfCompromise(
                value=url, ioc_type=IoCType.URL, source="extraction",
            ))

        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        for email in re.findall(email_pattern, text):
            iocs.append(IndicatorOfCompromise(
                value=email, ioc_type=IoCType.EMAIL, source="extraction",
            ))

        sha256_pattern = r'\b[a-fA-F0-9]{64}\b'
        for h in re.findall(sha256_pattern, text):
            iocs.append(IndicatorOfCompromise(
                value=h, ioc_type=IoCType.HASH_SHA256, source="extraction",
            ))

        sha1_pattern = r'\b[a-fA-F0-9]{40}\b'
        for h in re.findall(sha1_pattern, text):
            if not re.match(sha256_pattern, h):
                iocs.append(IndicatorOfCompromise(
                    value=h, ioc_type=IoCType.HASH_SHA1, source="extraction",
                ))

        md5_pattern = r'\b[a-fA-F0-9]{32}\b'
        for h in re.findall(md5_pattern, text):
            if not re.match(sha256_pattern, h) and not re.match(sha1_pattern, h):
                iocs.append(IndicatorOfCompromise(
                    value=h, ioc_type=IoCType.HASH_MD5, source="extraction",
                ))

        self._ioc_database.extend(iocs)
        return iocs

    async def lookup_ioc(self, ioc: IndicatorOfCompromise) -> IndicatorOfCompromise:
        ioc.confidence = self._calculate_confidence(ioc)
        ioc.threat_level = self._assess_threat_level(ioc)

        if ioc.ioc_type == IoCType.IP:
            await self._enrich_ip(ioc)
        elif ioc.ioc_type in (IoCType.DOMAIN, IoCType.URL):
            await self._enrich_domain(ioc)
        elif ioc.ioc_type in (IoCType.HASH_MD5, IoCType.HASH_SHA1, IoCType.HASH_SHA256):
            await self._enrich_hash(ioc)

        return ioc

    async def _enrich_ip(self, ioc: IndicatorOfCompromise) -> None:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"https://ip-api.com/json/{ioc.value}")
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("org", "").lower().startswith("tor"):
                        ioc.tags.append("tor_exit_node")
                        ioc.threat_level = ThreatLevel.HIGH
                    if data.get("proxy"):
                        ioc.tags.append("proxy")
        except Exception as exc:
            logger.warning("ip_enrichment_failed", ip=ioc.value, error=str(exc))

    async def _enrich_domain(self, ioc: IndicatorOfCompromise) -> None:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://www.virustotal.com/api/v3/domains/" + ioc.value,
                    headers={"x-apikey": ""},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    attrs = data.get("data", {}).get("attributes", {})
                    if attrs.get("last_analysis_stats", {}).get("malicious", 0) > 5:
                        ioc.threat_level = ThreatLevel.CRITICAL
                        ioc.confidence = 0.9
        except Exception:
            pass

    async def _enrich_hash(self, ioc: IndicatorOfCompromise) -> None:
        ioc.tags.append("malware_indicator")
        ioc.threat_level = ThreatLevel.HIGH
        ioc.confidence = 0.7

    def _calculate_confidence(self, ioc: IndicatorOfCompromise) -> float:
        confidence = 0.3
        if ioc.source == "misp" or ioc.source == "otx":
            confidence += 0.4
        if ioc.tags:
            confidence += 0.1 * len(ioc.tags)
        if ioc.mitre_techniques:
            confidence += 0.2
        return min(confidence, 1.0)

    def _assess_threat_level(self, ioc: IndicatorOfCompromise) -> ThreatLevel:
        if ioc.confidence >= 0.8:
            return ThreatLevel.CRITICAL
        if ioc.confidence >= 0.6:
            return ThreatLevel.HIGH
        if ioc.confidence >= 0.4:
            return ThreatLevel.MEDIUM
        return ThreatLevel.LOW

    def map_to_mitre(self, ioc: IndicatorOfCompromise) -> list[str]:
        techniques = []
        if ioc.ioc_type == IoCType.EMAIL:
            techniques.append("T1566")
        if ioc.ioc_type == IoCType.IP and "c2" in " ".join(ioc.tags).lower():
            techniques.append("T1071")
        if ioc.ioc_type in (IoCType.HASH_MD5, IoCType.HASH_SHA1, IoCType.HASH_SHA256):
            techniques.append("T1059")
        return techniques

    async def generate_threat_report(self, iocs: list[IndicatorOfCompromise]) -> ThreatReport:
        critical_iocs = [i for i in iocs if i.threat_level == ThreatLevel.CRITICAL]
        high_iocs = [i for i in iocs if i.threat_level == ThreatLevel.HIGH]

        all_techniques = set()
        for ioc in iocs:
            techniques = self.map_to_mitre(ioc)
            all_techniques.update(techniques)

        ttp_names = [self.MITRE_ATTACK_TECHNIQUES.get(t, t) for t in all_techniques]

        report = ThreatReport(
            title=f"Threat Intelligence Report — {len(iocs)} IOCs analyzed",
            threat_level=ThreatLevel.CRITICAL if critical_iocs else ThreatLevel.HIGH if high_iocs else ThreatLevel.MEDIUM,
            iocs=iocs,
            ttps=ttp_names,
            recommendations=[
                "Block all identified malicious IPs at the firewall",
                "Add identified hashes to endpoint protection quarantine list",
                "Monitor for identified TTPs in SIEM alerts",
                "Conduct threat hunting for identified IOCs across infrastructure",
            ],
        )
        return report

    def get_all_iocs(self) -> list[IndicatorOfCompromise]:
        return self._ioc_database

cybint = CYBINTModule()
