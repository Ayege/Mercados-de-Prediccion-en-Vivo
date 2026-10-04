"""Adaptador HTTP: traduce peticiones a casos de uso y errores a códigos de estado."""
from __future__ import annotations

import secrets
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from ...application.errors import Cooldown, NotFound
from ...application.ports import FAULTS
from ...application.service import MarketService
from ...domain.errors import MarketError
from .schemas import CensusAnswer, NewMarket, Trade

STATIC = Path(__file__).parent / "static"
Fault = Literal[tuple(FAULTS)]  # type: ignore[valid-type]


def create_app(service: MarketService, presenter_key: str = "", revision: str = "local") -> FastAPI:
    app = FastAPI(title="Oráculo — mercados de predicción", docs_url="/api/docs")

    def presenter_only(request: Request) -> None:
        """Crear y resolver mercados es del ponente, no de la audiencia.

        Sin `presenter_key` (desarrollo local) no se exige nada.
        """
        given = request.headers.get("x-presenter-key", "")
        if presenter_key and not secrets.compare_digest(given, presenter_key):
            raise HTTPException(403, "solo el ponente puede hacer esto")

    @app.exception_handler(MarketError)
    async def market_error(_: Request, exc: MarketError):
        code = 404 if isinstance(exc, NotFound) else 429 if isinstance(exc, Cooldown) else 400
        return JSONResponse({"detail": str(exc)}, status_code=code)

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    @app.get("/api/info")
    def info():
        o = service.oracle
        return {"oracle": o.name, "model": o.model, "revision": revision,
                "faults": FAULTS, "presenter_key_required": bool(presenter_key)}

    @app.get("/api/markets")
    def list_markets():
        return service.list()

    @app.post("/api/markets", status_code=201, dependencies=[Depends(presenter_only)])
    def create_market(body: NewMarket):
        return service.create(body.question.strip(), body.criteria.strip(), body.b,
                              body.kind, body.threshold)

    @app.get("/api/markets/{market_id}")
    def get_market(market_id: str):
        return service.view(market_id)

    @app.post("/api/markets/{market_id}/trade")
    def trade(market_id: str, body: Trade):
        return service.trade(market_id, body.user, body.outcome, body.amount)

    @app.post("/api/markets/{market_id}/census")
    def census(market_id: str, body: CensusAnswer):
        return service.answer_census(market_id, body.user, body.answer)

    @app.post("/api/markets/{market_id}/resolve", dependencies=[Depends(presenter_only)])
    async def resolve(market_id: str, fault: Fault | None = None):
        return await service.resolve(market_id, fault)

    @app.get("/api/users/{name}")
    def user(name: str):
        return service.account(name)

    app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
    return app
