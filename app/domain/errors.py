class MarketError(Exception):
    """Una orden o una operación viola una regla del mercado."""


class SimulationError(Exception):
    """Una operación sobre la simulación no es válida en su estado actual."""
