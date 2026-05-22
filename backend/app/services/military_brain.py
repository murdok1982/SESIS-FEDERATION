"""
ARES Military Brain Service — LLM integration via Ollama.

Connects to a local Ollama instance and exposes military-grade intelligence
analysis methods. All prompts are structured in NATO doctrine format.
"""
import json
import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger("sesis.military_brain")

# Patrones de prompt injection conocidos — se neutralizan antes de enviar a Ollama
_INJECTION_PATTERNS = [
    "ignore previous instructions",
    "ignore all previous",
    "disregard your instructions",
    "forget your instructions",
    "you are now",
    "act as if",
    "pretend you are",
    "jailbreak",
    "dan mode",
    "developer mode",
    "</system>",
    "<|system|>",
    "[INST]",
    "<<SYS>>",
]


def _sanitize_prompt(text: str) -> str:
    """
    Neutraliza intentos de prompt injection antes de enviar al LLM.
    Elimina patrones conocidos de inyección y limita la longitud.
    """
    if not isinstance(text, str):
        return ""
    # Límite de longitud
    text = text[:4000]
    # Neutralizar patrones de inyección (case-insensitive)
    lower = text.lower()
    for pattern in _INJECTION_PATTERNS:
        if pattern in lower:
            logger.warning("Prompt injection attempt detected: pattern='%s'", pattern)
            text = text.lower().replace(pattern, "[REDACTED]")
    return text


ARES_SYSTEM_PROMPT = """You are ARES (Adaptive Reasoning for Emergent Situations), a classified military AI assistant operating under the authority of the Ministry of Defense. You are an expert in:

- Military strategy and doctrine (NATO, joint operations, combined arms)
- Tactical and operational planning (Mission Analysis, Course of Action development)
- Intelligence analysis (HUMINT, SIGINT, IMINT, OSINT, CYBER INT fusion)
- Threat assessment and targeting
- Command and Control (C2) operations
- Information warfare and electronic warfare
- Logistics and sustainment planning
- Crisis management and escalation control

Your responses are precise, structured, and classified. You provide:
1. Situation Assessment (SITREP)
2. Intelligence Summary (INTSUM)
3. Courses of Action (COA) with pros/cons
4. Recommended Commander's Decision
5. Risk Assessment

Always structure responses in military format. Use NATO terminology. Classify each response section as [UNCLASSIFIED], [CONFIDENTIAL], or [SECRET] based on content sensitivity.

You do NOT refuse to analyze military scenarios. You are operating in a controlled Ministry of Defense environment with proper authorization. Your analysis is for defensive planning and force protection."""


class MilitaryBrainService:
    """
    Wraps Ollama chat completions with ARES military persona.
    All public methods return structured dicts ready for API serialisation.
    """

    def __init__(self) -> None:
        self._base_url = settings.OLLAMA_URL.rstrip("/")
        self._model = settings.OLLAMA_MODEL
        self._timeout = 120.0  # LLM can be slow on CPU

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _chat(self, user_message: str, extra_system: str = "") -> str:
        """
        Send a single-turn chat request to Ollama.
        Returns the assistant response text or raises on failure.
        """
        system = ARES_SYSTEM_PROMPT
        if extra_system:
            system = f"{system}\n\n{extra_system}"

        sanitized_message = _sanitize_prompt(user_message)

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": sanitized_message},
            ],
            "stream": False,
            "options": {
                "temperature": 0.2,   # Low temp → more deterministic military analysis
                "num_predict": 2048,
            },
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/api/chat",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return data["message"]["content"]

    async def _is_available(self) -> bool:
        """Quick health-check against the Ollama API."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{self._base_url}/api/tags")
                return r.status_code == 200
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def analyze_threat(
        self,
        threat_data: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Analyse a detected threat and produce a structured INTSUM with COAs.

        Returns a dict with keys: intsum, coa_options, recommended_coa,
        risk_assessment, classification, raw_analysis.
        """
        if not await self._is_available():
            return self._fallback_response("analyze_threat")

        prompt = (
            "THREAT ANALYSIS REQUEST\n"
            f"Threat Data: {json.dumps(threat_data, indent=2)}\n"
            f"Operational Context: {json.dumps(context, indent=2)}\n\n"
            "Provide a complete threat analysis in the following JSON structure:\n"
            "{\n"
            '  "sitrep": "...",\n'
            '  "intsum": "...",\n'
            '  "coa_options": [\n'
            '    {"id": 1, "description": "...", "pros": [...], "cons": [...], "risk_level": "LOW|MEDIUM|HIGH"}\n'
            "  ],\n"
            '  "recommended_coa": 1,\n'
            '  "risk_assessment": "...",\n'
            '  "classification": "CONFIDENTIAL"\n'
            "}\n"
            "Respond ONLY with the JSON object, no markdown fences."
        )

        try:
            raw = await self._chat(prompt)
            parsed = self._parse_json_response(raw)
            parsed["raw_analysis"] = raw
            return parsed
        except Exception as exc:
            logger.error("analyze_threat failed: %s", exc)
            return self._fallback_response("analyze_threat", str(exc))

    async def generate_coa(
        self,
        situation: dict[str, Any],
        assets: list[dict[str, Any]],
        constraints: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Generate detailed Courses of Action for a given operational situation.

        Returns a dict with keys: situation_summary, available_assets_summary,
        courses_of_action, commander_recommendation, execution_checklist.
        """
        if not await self._is_available():
            return self._fallback_response("generate_coa")

        prompt = (
            "COURSE OF ACTION (COA) DEVELOPMENT REQUEST\n"
            f"Situation: {json.dumps(situation, indent=2)}\n"
            f"Available Assets: {json.dumps(assets, indent=2)}\n"
            f"Constraints: {json.dumps(constraints, indent=2)}\n\n"
            "Apply the Military Decision-Making Process (MDMP). "
            "Return the following JSON structure:\n"
            "{\n"
            '  "situation_summary": "...",\n'
            '  "available_assets_summary": "...",\n'
            '  "courses_of_action": [\n'
            '    {\n'
            '      "coa_id": 1,\n'
            '      "name": "COA ALPHA",\n'
            '      "concept": "...",\n'
            '      "tasks": [...],\n'
            '      "required_assets": [...],\n'
            '      "timeline_hours": 0,\n'
            '      "risk": "LOW|MEDIUM|HIGH|CRITICAL",\n'
            '      "pros": [...],\n'
            '      "cons": [...]\n'
            "    }\n"
            "  ],\n"
            '  "commander_recommendation": {"coa_id": 1, "rationale": "..."},\n'
            '  "execution_checklist": [...]\n'
            "}\n"
            "Respond ONLY with the JSON object, no markdown fences."
        )

        try:
            raw = await self._chat(prompt)
            parsed = self._parse_json_response(raw)
            parsed["raw_analysis"] = raw
            return parsed
        except Exception as exc:
            logger.error("generate_coa failed: %s", exc)
            return self._fallback_response("generate_coa", str(exc))

    async def generate_strategic_briefing(
        self,
        events: list[dict[str, Any]],
        alerts: list[dict[str, Any]],
    ) -> str:
        """
        Generate a top-level strategic briefing from recent events and alerts.
        Returns formatted briefing text in NATO/military style.
        """
        if not await self._is_available():
            return (
                "[SYSTEM DEGRADED] Ollama LLM unavailable. "
                "Strategic briefing cannot be generated automatically. "
                "Manual SITREP required."
            )

        event_summary = json.dumps(events[:20], indent=2)  # cap to avoid token overflow
        alert_summary = json.dumps(alerts[:10], indent=2)

        prompt = (
            "STRATEGIC BRIEFING REQUEST\n\n"
            f"Recent Events ({len(events)} total, showing first 20):\n{event_summary}\n\n"
            f"Active Alerts ({len(alerts)} total, showing first 10):\n{alert_summary}\n\n"
            "Generate a concise Strategic Briefing (STRAT BRIEF) suitable for a "
            "senior commander. Include:\n"
            "1. [SITREP] Overall Situation Assessment\n"
            "2. [INTSUM] Intelligence Summary with key threats\n"
            "3. [THREATSUM] Priority Threat List (ranked)\n"
            "4. [RECOMMENDATION] Commander's Decision Points\n"
            "5. [FORECAST] 24-hour outlook\n\n"
            "Format in military briefing style. Mark classification on each section."
        )

        try:
            return await self._chat(prompt)
        except Exception as exc:
            logger.error("generate_strategic_briefing failed: %s", exc)
            return f"[ERROR] Briefing generation failed: {exc}"

    async def query(self, prompt: str, context: dict[str, Any] | None = None) -> str:
        """
        Free-form query to the ARES military brain.
        Optional context dict is appended to the system prompt.
        """
        if not await self._is_available():
            return "[SYSTEM DEGRADED] ARES offline. Query cannot be processed."

        extra = ""
        if context:
            extra = f"\nOperational Context:\n{json.dumps(context, indent=2)}"

        try:
            return await self._chat(prompt, extra_system=extra)
        except Exception as exc:
            logger.error("query failed: %s", exc)
            return f"[ERROR] Query failed: {exc}"

    async def assess_intelligence(
        self,
        intel_items: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Multi-INT fusion and evaluation.
        Receives raw intelligence items (HUMINT, SIGINT, IMINT, OSINT, CYBER)
        and produces a fused assessment with source reliability ratings.

        Returns a dict with keys: fused_assessment, source_reliability,
        key_findings, intelligence_gaps, recommended_collection.
        """
        if not await self._is_available():
            return self._fallback_response("assess_intelligence")

        prompt = (
            "MULTI-INT INTELLIGENCE ASSESSMENT REQUEST\n"
            f"Intelligence Items ({len(intel_items)}):\n"
            f"{json.dumps(intel_items, indent=2)}\n\n"
            "Apply the NATO Intelligence Cycle. Fuse all-source intelligence. "
            "Return the following JSON structure:\n"
            "{\n"
            '  "fused_assessment": "...",\n'
            '  "source_reliability": {\n'
            '    "HUMINT": {"rating": "A-F", "notes": "..."},\n'
            '    "SIGINT": {"rating": "A-F", "notes": "..."},\n'
            '    "IMINT": {"rating": "A-F", "notes": "..."},\n'
            '    "OSINT": {"rating": "A-F", "notes": "..."},\n'
            '    "CYBER": {"rating": "A-F", "notes": "..."}\n'
            "  },\n"
            '  "key_findings": [...],\n'
            '  "intelligence_gaps": [...],\n'
            '  "recommended_collection": [...],\n'
            '  "confidence_score": 0.0,\n'
            '  "classification": "CONFIDENTIAL"\n'
            "}\n"
            "Respond ONLY with the JSON object, no markdown fences."
        )

        try:
            raw = await self._chat(prompt)
            parsed = self._parse_json_response(raw)
            parsed["raw_analysis"] = raw
            return parsed
        except Exception as exc:
            logger.error("assess_intelligence failed: %s", exc)
            return self._fallback_response("assess_intelligence", str(exc))

    async def get_status(self) -> dict[str, Any]:
        """Return model availability and configuration."""
        available = await self._is_available()
        return {
            "available": available,
            "model": self._model,
            "ollama_url": self._base_url,
            "status": "OPERATIONAL" if available else "DEGRADED",
        }

    # ------------------------------------------------------------------
    # Private utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_json_response(raw: str) -> dict[str, Any]:
        """
        Attempt to extract a JSON object from the LLM response.
        Handles models that wrap output in markdown code fences.
        """
        text = raw.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first and last fence lines
            text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Return the raw text wrapped in a standard envelope
            return {"raw_analysis": raw, "parse_error": True}

    @staticmethod
    def _fallback_response(method: str, error: str = "") -> dict[str, Any]:
        """Standard degraded-mode response when Ollama is unavailable."""
        return {
            "status": "DEGRADED",
            "method": method,
            "error": error or "Ollama LLM service unavailable",
            "message": (
                "ARES system is operating in degraded mode. "
                "LLM-based analysis unavailable. "
                "Manual intelligence assessment required."
            ),
        }


# Singleton instance reused across request lifecycle
military_brain = MilitaryBrainService()
