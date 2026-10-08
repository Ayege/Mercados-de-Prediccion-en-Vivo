"""Editor y lectores simulados: ensayos sin red.

Nunca inventan titulares de medios reales: usan dos medios ficticios, con
dominios `.example`, y cada titular dice que es de ensayo.
"""
from __future__ import annotations

import hashlib
from datetime import date, timedelta

from ...domain.media import Article, Estimate, MediaList, NewsFind, Outlet

FICTION = "medio inventado para ensayar; no existe"
REHEARSAL = MediaList((
    Outlet("El Faro Progresista (ficticio)", "faro-progresista.example", "izquierda", FICTION),
    Outlet("La Tribuna Conservadora (ficticio)", "tribuna-conservadora.example", "derecha", FICTION),
), source="lista de ensayo con medios ficticios", rehearsal=True)


def _sign(text: str) -> int:
    return 1 if hashlib.sha256(text.encode()).digest()[0] % 2 == 0 else -1


class MockNewsDesk:
    name = "mock"
    model = "mock"

    async def find(self, topic: str, media: MediaList) -> NewsFind:
        deadline = (date.today() + timedelta(days=7)).strftime("%d/%m/%Y")
        raw = {
            "pregunta": f"¿Habrá un anuncio oficial sobre «{topic}» antes del {deadline}?",
            "criterio": f"[Simulación] SÍ si una fuente oficial publica un anuncio sobre «{topic}» "
                        f"con fecha igual o anterior al {deadline}.",
            "tipo": "futuro",
        }
        articles = [Article(f"[Ensayo] {o.name}: lo que se sabe de «{topic}»",
                            f"https://{o.domain}/ensayo", o) for o in REHEARSAL.outlets]
        trace = ["editor simulado, sin red: medios ficticios y titulares de ensayo",
                 f"{len(articles)} titular(es) de ensayo"]
        return NewsFind(raw, articles, trace, self.model)


class MockNewsReader:
    """Cada lado empuja en una dirección (cuál, depende de la pregunta). Ambas se cancelan."""

    name = "mock"
    model = "mock"

    async def estimate(self, question: str, criteria: str, articles: list[Article]) -> Estimate:
        sign = _sign(question)
        pull = sum(0.2 if a.outlet.lean == "izquierda" else -0.2 for a in articles) * sign
        p = min(0.95, max(0.05, 0.5 + pull))
        sides = sorted({a.outlet.lean for a in articles}) or ["ninguno"]
        return Estimate(p, f"[Simulación] leí {len(articles)} titular(es) de {', '.join(sides)}.")
