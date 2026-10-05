"""Nodo de la nube real: lo que corre en cada `oraculo-nodo-<región>`.

Misma imagen que la API, otro módulo (`APP_MODULE=app.node:app`). No guarda
estado ni importa nada del resto de la app. `NODO_FALLA` simula la falla que el
ponente inyecta, y una revisión nueva sin ella la repara.
"""
import asyncio
import hashlib
import os
import time

from fastapi import FastAPI, Response

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


# No /healthz: Cloud Run reserva las rutas que terminan en "z".
@app.get("/salud")
async def salud(response: Response) -> dict:
    fault = os.getenv("NODO_FALLA", "ninguna")
    if fault == "caida":
        response.status_code = 503
        return {"ok": False}
    if fault == "latencia":
        await asyncio.sleep(0.6)
    return {"ok": True, "region": os.getenv("NODO_REGION", ""), "revision": os.getenv("K_REVISION", "local")}


@app.get("/trabajo")
async def trabajo(response: Response) -> dict:
    """Una unidad de trabajo real y pequeña: lo que los agentes del mercado venden."""
    if os.getenv("NODO_FALLA") == "caida":
        response.status_code = 503
        return {"ok": False}
    start = time.perf_counter()
    digest = b"oraculo"
    for _ in range(2000):  # unos pocos milisegundos de CPU real
        digest = hashlib.sha256(digest).digest()
    elapsed = round((time.perf_counter() - start) * 1000, 2)
    return {"ok": True, "agente": os.getenv("AGENTE_ID", ""), "server_ms": elapsed}
