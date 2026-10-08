"""Adaptador HTTP: traduce peticiones a casos de uso y errores a códigos de estado.

Aquí viven los controles de borde, todos en un solo archivo para poder revisarlos
de una vez (ver SECURITY.md):

- Ponente: cabecera `X-Presenter-Key`, comparada en tiempo constante.
- Audiencia: cabecera `X-User-Token`, emitida una sola vez al entrar con un nombre.
- Cloud Scheduler: token OIDC de Google verificado (audiencia y cuenta), sin secretos compartidos.
- Cabeceras de seguridad y CSP estricta para scripts en todas las respuestas.
- La vista pública de la infraestructura no muestra errores internos ni deja
  que cualquiera mantenga vivos los nodos.
"""
from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from ...application.cloud import CloudService
from ...application.errors import Conflict, Cooldown, NotFound, RateLimited, Unauthorized
from ...application.infra import InfraController
from ...application.news import NewsService
from ...application.ports import FAULTS, FRAMING_FAULTS
from ...application.service import MarketService
from ...domain.errors import MarketError, SimulationError
from ...domain.framing import Framing, Headline
from .schemas import CensusAnswer, Enter, FramingIn, InjectFault, NewMarket, RealFault, Topic, Trade

STATIC = Path(__file__).parent / "static"
Fault = Literal[tuple(FAULTS | FRAMING_FAULTS)]  # type: ignore[valid-type]


def to_framing(body: FramingIn | None) -> Framing | None:
    if body is None:
        return None
    return Framing(Headline(**body.pro_si.model_dump()), Headline(**body.pro_no.model_dump()))

# Scripts solo desde el propio origen: ningún script en línea, ningún dominio externo.
# Los estilos en línea se permiten porque los gráficos SVG los usan; inyectar estilo es mucho
# menos grave que inyectar script.
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
       "connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
SECURITY_HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
}
STATUS = {NotFound: 404, Unauthorized: 401, Conflict: 409, Cooldown: 429, RateLimited: 429}

SchedulerCheck = Callable[[str], Awaitable[bool]]


def create_app(service: MarketService, cloud: CloudService, infra: InfraController | None = None,
               presenter_key: str = "", revision: str = "local", docs: bool = True,
               scheduler_check: SchedulerCheck | None = None, news: NewsService | None = None) -> FastAPI:
    app = FastAPI(title="Oráculo — mercados de predicción", docs_url="/api/docs" if docs else None,
                  redoc_url=None, openapi_url="/openapi.json" if docs else None)

    @app.middleware("http")
    async def harden(request: Request, call_next):
        if infra and request.url.path.startswith("/api/") and not request.url.path.startswith("/api/infra"):
            infra.count_request()  # cada petición de la sala es demanda real para el autoescalado
        response = await call_next(request)
        response.headers.update(SECURITY_HEADERS)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    def is_presenter(request: Request) -> bool:
        """Sin `presenter_key` (desarrollo local) todos son ponente. En Cloud Run, main.py
        se niega a arrancar sin una clave fuerte."""
        given = request.headers.get("x-presenter-key", "")
        return not presenter_key or secrets.compare_digest(given.encode(), presenter_key.encode())

    def presenter_only(request: Request) -> None:
        if not is_presenter(request):
            raise HTTPException(403, "solo el ponente puede hacer esto")

    async def presenter_or_scheduler(request: Request) -> None:
        if is_presenter(request):
            return
        auth = request.headers.get("authorization", "")
        if scheduler_check and auth.startswith("Bearer ") and await scheduler_check(auth[7:]):
            return
        raise HTTPException(403, "solo el ponente o Cloud Scheduler pueden hacer esto")

    @app.exception_handler(MarketError)
    async def market_error(_: Request, exc: MarketError):
        code = next((c for kind, c in STATUS.items() if isinstance(exc, kind)), 400)
        return JSONResponse({"detail": str(exc)}, status_code=code)

    @app.exception_handler(SimulationError)
    async def simulation_error(_: Request, exc: SimulationError):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    # Cloud Run reserva las rutas que terminan en "z": en producción, usa /api/salud.
    @app.get("/healthz")
    @app.get("/api/salud")
    def healthz():
        return {"ok": True}

    @app.get("/api/info")
    def info():
        o = service.oracle
        return {"oracle": o.name, "model": o.model, "revision": revision,
                "faults": FAULTS, "framing_faults": FRAMING_FAULTS,
                "presenter_key_required": bool(presenter_key),
                "news": news.media.summary() if news else None,
                "infra": infra.mode if infra else "apagado"}

    # --- audiencia ---------------------------------------------------------------
    @app.post("/api/entrar", status_code=201)
    def enter(body: Enter):
        return service.enter(body.name)

    @app.get("/api/markets")
    def list_markets():
        return service.list()

    @app.get("/api/markets/{market_id}")
    def get_market(market_id: str):
        return service.view(market_id)

    @app.post("/api/markets/{market_id}/trade")
    def trade(market_id: str, body: Trade, x_user_token: str = Header("", max_length=64)):
        return service.trade(market_id, body.user, x_user_token, body.outcome, body.amount)

    @app.post("/api/markets/{market_id}/census")
    def census(market_id: str, body: CensusAnswer, x_user_token: str = Header("", max_length=64)):
        return service.answer_census(market_id, body.user, x_user_token, body.answer)

    @app.get("/api/users/{name}")
    def user(name: str, x_user_token: str = Header("", max_length=64)):
        return service.account(name, x_user_token)

    # --- ponente: mercados ---------------------------------------------------------
    @app.post("/api/markets", status_code=201, dependencies=[Depends(presenter_only)])
    def create_market(body: NewMarket):
        return service.create(body.question.strip(), body.criteria.strip(), body.b,
                              body.kind, body.threshold, body.predicate, to_framing(body.framing))

    @app.post("/api/markets/{market_id}/revelar", dependencies=[Depends(presenter_only)])
    def reveal(market_id: str):
        return service.reveal(market_id)

    @app.post("/api/markets/{market_id}/resolve", dependencies=[Depends(presenter_only)])
    async def resolve(market_id: str, fault: Fault | None = None):
        return await service.resolve(market_id, fault)

    # --- ponente: preguntas desde las noticias -------------------------------------
    def need_news() -> NewsService:
        if news is None:
            raise HTTPException(409, "las preguntas desde noticias no están conectadas")
        return news

    @app.get("/api/noticias", dependencies=[Depends(presenter_only)])
    def news_view():
        return need_news().view()

    @app.post("/api/noticias/borradores", status_code=201, dependencies=[Depends(presenter_only)])
    async def news_propose(body: Topic):
        return await need_news().propose(body.topic.strip())

    @app.post("/api/noticias/borradores/{draft_id}/abrir", status_code=201,
              dependencies=[Depends(presenter_only)])
    def news_open(draft_id: str):
        return need_news().open(draft_id)

    @app.delete("/api/noticias/borradores/{draft_id}", status_code=204,
                dependencies=[Depends(presenter_only)])
    def news_discard(draft_id: str):
        need_news().discard(draft_id)

    @app.post("/api/markets/{market_id}/agentes", dependencies=[Depends(presenter_only)])
    async def news_agents(market_id: str):
        return await need_news().consult_agents(market_id)

    # --- nube simulada -----------------------------------------------------------
    @app.get("/api/nube")
    def cloud_view():
        return cloud.view()

    @app.post("/api/nube/iniciar", dependencies=[Depends(presenter_only)])
    def cloud_start():
        return cloud.start()

    @app.post("/api/nube/pausar", dependencies=[Depends(presenter_only)])
    def cloud_pause():
        return cloud.pause()

    @app.post("/api/nube/avanzar", dependencies=[Depends(presenter_only)])
    def cloud_step(n: int = 1):
        return cloud.step(n)

    @app.post("/api/nube/fallas", dependencies=[Depends(presenter_only)])
    def cloud_inject(body: InjectFault):
        return cloud.inject(body.kind, body.target)

    @app.post("/api/nube/topologias", dependencies=[Depends(presenter_only)])
    async def cloud_propose(fuente: Literal["generativo", "evolutivo"]):
        return await cloud.propose(fuente)

    # --- infraestructura real ---------------------------------------------------
    def need_infra() -> InfraController:
        if infra is None:
            raise HTTPException(409, "la infraestructura real está apagada (INFRA_MODE=apagado)")
        return infra

    @app.get("/api/infra")
    async def infra_view(request: Request):
        if infra is None:
            return {"mode": "apagado"}
        if is_presenter(request):
            # Solo el ponente mueve el reloj del controlador y cuenta como «alguien mira».
            # Si cualquiera pudiera, bastaría con consultar esta URL para que la vigilia
            # nunca apagara los nodos.
            infra.touch()
            await infra.maybe_cycle()
            return infra.view()
        return infra.view(detailed=False)

    @app.post("/api/infra/vigilia", dependencies=[Depends(presenter_or_scheduler)])
    async def infra_vigil():
        return await need_infra().vigil()

    @app.post("/api/infra/actuar", dependencies=[Depends(presenter_only)])
    def infra_toggle(activo: bool):
        need_infra().set_active(activo)
        return need_infra().view()

    @app.post("/api/infra/ciclo", dependencies=[Depends(presenter_only)])
    async def infra_cycle():
        await need_infra().cycle()
        return need_infra().view()

    @app.post("/api/infra/fallas", dependencies=[Depends(presenter_only)])
    async def infra_fault(body: RealFault):
        await need_infra().inject(body.region, body.kind)
        return need_infra().view()

    @app.post("/api/infra/apagar", dependencies=[Depends(presenter_only)])
    async def infra_shutdown():
        await need_infra().shutdown()
        return need_infra().view()

    app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
    return app
