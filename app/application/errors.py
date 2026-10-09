from __future__ import annotations

from typing import TYPE_CHECKING

from ..domain.errors import MarketError

if TYPE_CHECKING:
    from ..domain.market import Market
    from .ports import Repository


class NotFound(MarketError):
    pass


class Cooldown(MarketError):
    pass


class Unauthorized(MarketError):
    pass


class Conflict(MarketError):
    pass


class RateLimited(MarketError):
    pass


def require_market(repo: Repository, market_id: str) -> Market:
    """El mercado, o 404. Llamar dentro de una transacción."""
    m = repo.get_market(market_id)
    if m is None:
        raise NotFound("mercado no encontrado")
    return m
