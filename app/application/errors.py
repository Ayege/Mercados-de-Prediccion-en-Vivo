from ..domain.errors import MarketError


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
