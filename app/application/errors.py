from ..domain.errors import MarketError


class NotFound(MarketError):
    pass


class Cooldown(MarketError):
    pass
