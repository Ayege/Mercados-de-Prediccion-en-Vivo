"""Preguntas que nacen de las noticias del día, y agentes que leen esas noticias.

1. El ponente da un tema. `NewsDesk` busca noticias recientes en la lista de
   medios, propone una pregunta y devuelve solo titulares verificados.
2. `NewsPolicy` decide si el borrador sirve: pregunta de sí o no, criterio,
   y al menos un titular verificado de cada lado. El ponente la abre.
3. Cuando el ponente quiere, cuatro agentes leen la cobertura según su dieta
   de medios (izquierda, derecha, ambas, ninguna), estiman P(SÍ) y apuestan en
   el mismo mercado que la sala, uno tras otro, contra el precio del momento.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Callable

from ..domain.errors import MarketError
from ..domain.media import AGENTS, AgentRead, MediaList, NewsDraft, NewsPolicy, read_for, stake_for
from .errors import Cooldown, NotFound
from .ports import NewsDesk, NewsReader
from .service import MarketService
from .views import draft_view, market_view


class NewsService:
    def __init__(self, markets: MarketService, desk: NewsDesk, reader: NewsReader, media: MediaList,
                 policy: NewsPolicy | None = None, agent_budget: float = 200.0, cooldown: float = 30.0,
                 clock: Callable[[], float] = time.time,
                 new_id: Callable[[], str] = lambda: uuid.uuid4().hex[:8]):
        self.markets = markets
        self.desk = desk
        self.reader = reader
        self.media = media
        self.policy = policy or NewsPolicy()
        self.agent_budget = agent_budget
        self.cooldown = cooldown
        self.clock = clock
        self.new_id = new_id
        self.drafts: dict[str, NewsDraft] = {}
        self._last_search = -cooldown
        self._consulted: set[str] = set()

    def view(self) -> dict:
        return {"media": self.media.summary(), "desk": {"name": self.desk.name, "model": self.desk.model},
                "drafts": [draft_view(d) for d in reversed(self.drafts.values())]}

    async def propose(self, topic: str) -> dict:
        if not self.media.ready:
            raise MarketError("falta la lista de medios: define al menos un medio de izquierda y uno de "
                              "derecha en el archivo de MEDIOS_ARCHIVO")
        wait = self.cooldown - (self.clock() - self._last_search)
        if wait > 0:
            raise Cooldown(f"espera {int(wait) + 1} s antes de buscar otra vez")
        self._last_search = self.clock()
        find = await self.desk.find(topic, self.media)
        draft = self.policy.check(self.new_id(), topic, find)
        self.drafts[draft.id] = draft
        while len(self.drafts) > 10:
            self.drafts.pop(next(iter(self.drafts)))
        return draft_view(draft)

    def _draft(self, draft_id: str) -> NewsDraft:
        d = self.drafts.get(draft_id)
        if d is None:
            raise NotFound("borrador no encontrado")
        return d

    def open(self, draft_id: str) -> dict:
        d = self._draft(draft_id)
        if not d.accepted:
            raise MarketError("la política rechazó este borrador: busca otra vez")
        if d.market_id:
            raise MarketError("esta pregunta ya está abierta")
        m = self.markets.create(d.question, d.criteria, kind=d.kind, topic=d.topic, coverage=d.articles)
        d.market_id = m["id"]
        return m

    def discard(self, draft_id: str) -> None:
        self._draft(draft_id)
        del self.drafts[draft_id]

    async def consult_agents(self, market_id: str) -> dict:
        """Cada agente lee su dieta, estima y apuesta. Una vez por pregunta: cuesta llamadas."""
        with self.markets.repo.transaction():
            m = self.markets._market(market_id)
            m.ensure_open()
            if not m.coverage:
                raise MarketError("esta pregunta no salió de las noticias: no hay cobertura que leer")
            if market_id in self._consulted:
                raise MarketError("los agentes ya opinaron en esta pregunta")
            self._consulted.add(market_id)
            question, criteria, coverage = m.question, m.criteria, list(m.coverage)
        diets = list(AGENTS.items())
        estimates = await asyncio.gather(
            *(self.reader.estimate(question, criteria, read_for(diet, coverage)) for _, diet in diets))
        reads = []
        # Uno tras otro: cada agente ve el precio que dejó el anterior, como cualquier persona de la sala.
        for (agent, diet), e in zip(diets, estimates, strict=True):
            with self.markets.repo.transaction():
                m = self.markets._market(market_id)
                price, q, b = m.prices()["YES"], list(m.q), m.b
            outcome, stake = stake_for(e.p, q, b, self.agent_budget)
            read = AgentRead(agent, diet, read_for(diet, coverage), e.p, e.reasoning, price, outcome, stake)
            if outcome:
                _, read.shares = self.markets.agent_trade(market_id, agent, outcome, stake)
            reads.append(read)
        with self.markets.repo.transaction():
            m = self.markets._market(market_id)
            m.agent_reads = reads
            return market_view(m)
