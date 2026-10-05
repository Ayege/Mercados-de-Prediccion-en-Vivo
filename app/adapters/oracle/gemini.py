"""Ruta común para cualquier respuesta con forma de `generateContent` de Gemini.

Todos los adaptadores del oráculo pasan por `run → inject_fault → interpret`
y terminan en `AcceptancePolicy.apply`. Por eso los fallos inyectados en el
escenario ejercitan el mismo código que lee a Vertex AI en producción.

La evidencia no la escribe el modelo: sale de `groundingMetadata`, que Vertex AI
adjunta según lo que realmente buscó. Un modelo puede inventar una cita en su
texto; no puede inventar un grounding chunk.
"""
from __future__ import annotations

import copy
import json
from collections.abc import Awaitable, Callable

from ...application.ports import FAULTS
from ...domain.verdict import AcceptancePolicy, Proposal, Source, Verdict

Call = Callable[[str, str], Awaitable[dict]]


class NetworkDown(Exception):
    pass


def parse_verdict(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("la respuesta no contiene JSON")
    return json.loads(text[start : end + 1])


def normalize_sources(chunks: list[dict]) -> list[Source]:
    """Convierte groundingChunks de Vertex AI en evidencia con dominio real.

    Importante: `uri` es un enlace de redirección de vertexaisearch.cloud.google.com,
    así que todos los chunks comparten host. Contar dominios sobre `uri` daría
    siempre 1. El dominio verdadero viene en `domain` o, si falta, en `title`.
    """
    out = []
    for chunk in chunks or []:
        web = chunk.get("web") or {}
        uri = str(web.get("uri", ""))
        if not uri.startswith("https://"):
            continue
        domain = str(web.get("domain") or web.get("title") or "").strip().lower()
        domain = domain.removeprefix("www.")
        if not domain:
            continue
        out.append(Source(claim=str(web.get("title", ""))[:200], url=uri[:800], domain=domain))
    return out[:8]


def inject_fault(payload: dict, fault: str | None, trace: list[str]) -> dict:
    """Corrompe una respuesta para ensayar la política en vivo.

    Opera sobre el payload crudo, así que funciona igual con el modelo real que
    con el simulado. `red_caida` no llega aquí: se inyecta antes de la llamada.
    """
    if not fault:
        return payload
    trace.append(f"fallo inyectado: {fault} ({FAULTS[fault]})")
    payload = copy.deepcopy(payload)
    candidate = (payload.get("candidates") or [{}])[0]
    parts = candidate.setdefault("content", {}).setdefault("parts", [{"text": ""}])
    if fault == "json_malformado":
        parts[:] = [{"text": "Según mis búsquedas, la respuesta es claramente SÍ."}]
    elif fault == "baja_confianza":
        text = "".join(p.get("text", "") for p in parts)
        try:
            raw = parse_verdict(text)
        except ValueError:
            raw = {"outcome": "YES", "reasoning": ""}
        if raw.get("outcome") not in ("YES", "NO"):
            raw["outcome"] = "YES"
        raw["confidence"] = 0.55
        parts[:] = [{"text": json.dumps(raw, ensure_ascii=False)}]
    elif fault == "un_dominio":
        meta = candidate.setdefault("groundingMetadata", {})
        tagged = [(c, normalize_sources([c])) for c in meta.get("groundingChunks") or []]
        tagged = [(c, src[0].domain) for c, src in tagged if src]
        first = tagged[0][1] if tagged else None
        meta["groundingChunks"] = [c for c, domain in tagged if domain == first]
    return payload


def interpret(payload: dict, model: str, trace: list[str], policy: AcceptancePolicy) -> Verdict:
    """Lee una respuesta de generateContent y la somete a la política."""
    candidate = (payload.get("candidates") or [{}])[0]
    text = "".join(p.get("text", "") for p in candidate.get("content", {}).get("parts", [])
                   if not p.get("thought"))

    meta = candidate.get("groundingMetadata") or {}
    evidence = normalize_sources(meta.get("groundingChunks", []))
    queries = meta.get("webSearchQueries") or []
    suggestions = (meta.get("searchEntryPoint") or {}).get("renderedContent", "")
    trace.append(f"{len(queries)} búsqueda(s), {len(evidence)} fuente(s) devueltas por grounding")

    try:
        raw = parse_verdict(text)
    except ValueError:
        trace.append(f"respuesta no parseable (finishReason {candidate.get('finishReason', '?')}) "
                     "→ UNRESOLVED (fail-closed)")
        return policy.unreachable(model, trace, evidence, "Veredicto inválido.")
    return policy.apply(Proposal.from_raw(raw), evidence, model, trace, suggestions)


async def run(call: Call, question: str, criteria: str, model: str, trace: list[str],
              policy: AcceptancePolicy, fault: str | None = None) -> Verdict:
    """Llamada, fallo inyectado e interpretación. Nunca lanza por un fallo del modelo."""
    if fault and fault not in FAULTS:
        raise ValueError(f"fallo desconocido: {fault}")
    try:
        if fault == "red_caida":
            trace.append(f"fallo inyectado: {fault} ({FAULTS[fault]})")
            raise NetworkDown("conexión rechazada")
        payload = await call(question, criteria)
    except Exception as exc:
        trace.append(f"error al llamar al modelo ({type(exc).__name__}) → UNRESOLVED (fail-closed)")
        return policy.unreachable(model, trace)
    return interpret(inject_fault(payload, fault, trace), model, trace, policy)
