from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .market import Cooldown, Engine, MarketError, NotFound
from .oracle import get_oracle

STATIC = Path(__file__).parent / "static"

SEEDS = [
    (
        "¿Se publicó Kubernetes v1.36 antes del 30 de septiembre de 2026?",
        "SÍ si existe una release estable v1.36.0 en github.com/kubernetes/kubernetes "
        "con fecha igual o anterior al 30/09/2026.",
        60,
    ),
    (
        "¿Cerrará el USD/DOP por encima de 65 el 31 de diciembre de 2026?",
        "SÍ si la tasa de venta publicada por el Banco Central de la República Dominicana "
        "para el 31/12/2026 es mayor que 65.00. Antes de esa fecha no se puede resolver.",
        35,
    ),
    (
        "¿Se publicó Python 3.15.0 (versión final) antes del 15 de octubre de 2026?",
        "SÍ si python.org muestra la release 3.15.0 final con fecha igual o anterior al "
        "15/10/2026.",
        50,
    ),
]


class NewMarket(BaseModel):
    question: str = Field(min_length=8, max_length=200)
    criteria: str = Field(min_length=8, max_length=600)
    b: float = Field(100, ge=10, le=1000)


class Trade(BaseModel):
    user: str = Field(min_length=1, max_length=24)
    outcome: Literal["YES", "NO"]
    amount: float = Field(gt=0, le=10_000)


def seed(engine: Engine) -> None:
    engine._user("mercado")["balance"] = 1_000_000
    for question, criteria, yes_spend in SEEDS:
        m = engine.create(question, criteria)
        engine.trade(m["id"], "mercado", "YES", yes_spend)
        engine.trade(m["id"], "mercado", "NO", yes_spend * 0.4)


def create_app(engine: Engine | None = None, with_seed: bool = True) -> FastAPI:
    engine = engine or Engine(get_oracle())
    if with_seed:
        seed(engine)
    app = FastAPI(title="Oráculo — mercados de predicción", docs_url="/api/docs")

    @app.exception_handler(MarketError)
    async def market_error(_: Request, exc: MarketError):
        code = 404 if isinstance(exc, NotFound) else 429 if isinstance(exc, Cooldown) else 400
        return JSONResponse({"detail": str(exc)}, status_code=code)

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    @app.get("/api/info")
    def info():
        o = engine.oracle
        return {"oracle": o.name, "model": getattr(o, "model", "mock"),
                "revision": os.getenv("K_REVISION", "local")}

    @app.get("/api/markets")
    def list_markets():
        return engine.list()

    @app.post("/api/markets", status_code=201)
    def create_market(body: NewMarket):
        return engine.create(body.question.strip(), body.criteria.strip(), body.b)

    @app.get("/api/markets/{market_id}")
    def get_market(market_id: str):
        return engine.view(market_id)

    @app.post("/api/markets/{market_id}/trade")
    def trade(market_id: str, body: Trade):
        return engine.trade(market_id, body.user, body.outcome, body.amount)

    @app.post("/api/markets/{market_id}/resolve")
    async def resolve(market_id: str):
        return await engine.resolve(market_id)

    @app.get("/api/users/{name}")
    def user(name: str):
        return engine.user_view(name)

    app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
    return app


app = create_app()
