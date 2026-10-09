"""Qué puede preguntar la sala sobre la nube, y quién lo resuelve."""

SIMULATED = {
    "cooperacion_g5": "Al cerrar la generación 5, más del 40 % de los agentes es cooperativo.",
    "autorreparacion": "La primera caída de nodo queda reparada en menos de 6 ticks desde que ocurre.",
    "topologia_llm": "La primera topología del modelo generativo pasa la política.",
    "credulidad_g5": "Al cerrar la generación 5, la credulidad media de los agentes es menor que al empezar.",
}
REAL = {
    "autorreparacion_real": "La primera falla inyectada en un nodo real de Cloud Run queda reparada "
                            "en menos de 120 segundos.",
    "cooperacion_real": "Al cerrar la generación 3 del mercado real, la cooperación media de los agentes "
                        "es mayor que al empezar.",
}
PREDICATES = SIMULATED | REAL
