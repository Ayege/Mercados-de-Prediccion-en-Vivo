"""Oráculo simulado: ensayos y tests, sin tocar la red.

Devuelve un payload con la forma exacta de generateContent, así que pasa por
`interpret` y la política igual que el adaptador real.

Ante un titular se porta como un modelo con buenas defensas: si la noticia llega
como dato no confiable, la ignora. Si llega como hecho verificado (el fallo
`noticia_como_verdad`), la cree y responde hacia donde empuja.
"""
from __future__ import annotations

import hashlib
import json
import os

from ...application.ports import OracleQuery
from ...domain.verdict import VALID, AcceptancePolicy, Verdict
from .gemini import run


class MockOracle:
    name = "mock"
    model = "mock"

    def __init__(self, policy: AcceptancePolicy | None = None):
        self.policy = policy or AcceptancePolicy()

    async def _call(self, query: OracleQuery) -> dict:
        question, news = query.question, query.news
        # Se lee en cada llamada para poder fijar el veredicto durante un ensayo.
        force = os.getenv("ORACLE_MOCK_FORCE", "").upper()
        digest = hashlib.sha256(question.encode()).digest()
        outcome = force if force in VALID else ("YES" if digest[0] % 2 == 0 else "NO")
        if news and news.trusted and outcome != "UNRESOLVED":
            outcome = news.lean
        chunks = [] if outcome == "UNRESOLVED" else [
            {"web": {"uri": "https://example.com/a", "title": "Fuente A", "domain": "example.com"}},
            {"web": {"uri": "https://example.org/b", "title": "Fuente B", "domain": "example.org"}},
        ]
        raw = {
            "outcome": outcome,
            "confidence": 0.9,
            "reasoning": "[Simulación] Veredicto determinista para la demo; no consultó la web.",
        }
        return {"candidates": [{
            "content": {"parts": [{"text": json.dumps(raw, ensure_ascii=False)}]},
            "groundingMetadata": {"groundingChunks": chunks,
                                  "webSearchQueries": ["simulada"] if chunks else []},
        }]}

    async def resolve(self, query: OracleQuery) -> Verdict:
        trace = ["oráculo simulado, sin red"]
        return await run(self._call, query, self.model, trace, self.policy)
