import asyncio
import logging
from typing import Optional
from app.core.config import settings

logger = logging.getLogger(__name__)

PERSONAS = {
    "c2_analyst": "Eres un analista C4ISR experto en doctrina OTAN. "
                  "Analiza amenazas tácticas y recomienda cursos de accion.",
    "imint_analyst": "Eres un analista IMINT de imagenes satelitales. "
                     "Describe instalaciones militares, vehículos y cambios en el terreno.",
    "osint_analyst": "Eres un analista de inteligencia de fuentes abiertas. "
                     "Correlaciona eventos multi-fuente y evalua su confiabilidad.",
    "intel_analyst": "Eres un analista de inteligencia estrategica. "
                     "Genera briefings de situacion y evaluaciones de amenaza.",
    "opord_planner": "Eres un oficial de planeamiento de operaciones. "
                     "Redacta ordenes de operacion (OPORD) segun estandar OTAN.",
    "wargaming_sim": "Eres un simulador de wargaming tactico. "
                     "Evalua cursos de accion y predice resultados.",
    "psyops_planner": "Eres un especialista en operaciones psicologicas. "
                      "Disena mensajes y campanas de influencia.",
}


class LLMOrchestrator:
    def __init__(self):
        self._client = None
        self._rate_limit = asyncio.Semaphore(3)

    async def _get_client(self):
        if self._client is None:
            import httpx
            self._client = httpx.AsyncClient(timeout=settings.OLLAMA_TIMEOUT)
        return self._client

    async def query(self, persona: str, prompt: str, context: dict = None) -> str:
        system_prompt = PERSONAS.get(persona, PERSONAS["intel_analyst"])
        full_prompt = system_prompt + "\n\n"
        if context:
            full_prompt += f"Contexto: {context}\n\n"
        full_prompt += prompt

        async with self._rate_limit:
            try:
                client = await self._get_client()
                resp = await client.post(
                    f"{settings.OLLAMA_BASE_URL}/api/generate",
                    json={"model": settings.OLLAMA_MODEL, "prompt": full_prompt, "stream": False},
                )
                result = resp.json().get("response", "")
                logger.info(f"LLM [{persona}]: {len(result)} chars")
                return result
            except Exception as e:
                logger.warning(f"LLM primary failed ({e}), trying fallback...")
                return await self._fallback(persona, full_prompt)

    async def _fallback(self, persona: str, prompt: str) -> str:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{settings.OLLAMA_BASE_URL}/api/generate",
                    json={"model": "qwen2.5:1.5b", "prompt": prompt, "stream": False},
                )
                return resp.json().get("response", "")
        except Exception as e:
            logger.error(f"LLM fallback failed: {e}")
            return f"[ERROR] LLM no disponible: {e}"


llm = LLMOrchestrator()
