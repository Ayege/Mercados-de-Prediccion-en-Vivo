"""Juegos de preguntas que se siembran al arrancar (ver docs/PREGUNTAS.md).

Se elige con SEED_SET; varios juegos se combinan con «+» (por ejemplo,
`encuadre+nube_real`).
"""
from __future__ import annotations

from .application.service import MarketService
from .domain.framing import Framing, Headline

KUBERNETES = (
    "¿Se publicó Kubernetes v1.36 antes del 30 de septiembre de 2026?",
    "SÍ si existe una release estable v1.36.0 en github.com/kubernetes/kubernetes "
    "con fecha igual o anterior al 30/09/2026.",
    "presente",
)
PYTHON = (
    "¿Se publicó Python 3.15.0 (versión final) antes del 15 de octubre de 2026?",
    "SÍ si python.org muestra la release 3.15.0 final con fecha igual o anterior al 15/10/2026.",
    "presente",
)
DOLAR = (
    "¿Cerrará el USD/DOP por encima de 65 el 31 de diciembre de 2026?",
    "SÍ si la tasa de venta publicada por el Banco Central de la República Dominicana "
    "para el 31/12/2026 es mayor que 65.00. Antes de esa fecha no se puede resolver.",
    "futuro",
)
VIERNES = (
    "¿Más de la mitad de esta sala desplegó a producción un viernes en los últimos 30 días?",
    "Censo privado de la sala: SÍ si más del 50% de quienes respondan dice que sí.",
    "sala",
)
LLM = (
    "¿Más de la mitad de esta sala hizo merge esta semana de código generado por un LLM "
    "sin reescribirlo?",
    "Censo privado de la sala: SÍ si más del 50% de quienes respondan dice que sí.",
    "sala",
)
ROLLBACK = (
    "¿Más de la mitad de esta sala tuvo que revertir un despliegue en el último trimestre?",
    "Censo privado de la sala: SÍ si más del 50% de quienes respondan dice que sí.",
    "sala",
)
# Las mismas preguntas, con dos titulares sobre el mismo hecho. Son titulares de ensayo,
# escritos para la demo y marcados así en pantalla. Para usarlos en serio, cámbialos por
# titulares reales con su enlace; nunca atribuyas a un medio un titular que no publicó.
ENSAYO = "titular de ensayo"
PYTHON_ENCUADRADO = PYTHON + (Framing(
    pro_si=Headline("Python 3.15 entra en la recta final: las candidatas llegan según el calendario",
                    ENSAYO),
    pro_no=Headline("Python 3.15 sigue en candidatas: los mantenedores advierten que la fecha puede moverse",
                    ENSAYO),
),)
KUBERNETES_ENCUADRADO = KUBERNETES + (Framing(
    pro_si=Headline("Kubernetes mantiene su ritmo de tres versiones al año, como marca su calendario",
                    ENSAYO),
    pro_no=Headline("Kubernetes pisa el freno: la comunidad discute espaciar más sus versiones", ENSAYO),
),)
# Preguntas sobre la nube simulada: comportamiento emergente que resuelve el código.
COOPERACION = (
    "¿Al cerrar la generación 5, más del 40 % de los agentes será cooperativo?",
    "Lo resuelve la simulación: proporción de agentes con cooperación ≥ 0.6 al cerrar la generación 5.",
    "simulacion",
    "cooperacion_g5",
)
AUTORREPARACION = (
    "¿La primera caída de nodo quedará reparada en menos de 6 ticks?",
    "Lo resuelve la simulación: ticks entre la caída y el reemplazo sano del nodo.",
    "simulacion",
    "autorreparacion",
)
TOPOLOGIA = (
    "¿La primera topología que proponga el modelo generativo pasará la política?",
    "Lo resuelve la simulación: presupuesto, 2 regiones, disponibilidad 99,99 %, latencia ≤ 75 ms.",
    "simulacion",
    "topologia_llm",
)
CREDULIDAD = (
    "¿Al cerrar la generación 5, los agentes serán menos crédulos que al empezar?",
    "Lo resuelve la simulación: credulidad media al cerrar la generación 5 contra la inicial. Las "
    "noticias alarmistas aciertan el 30 % de las veces.",
    "simulacion",
    "credulidad_g5",
)
AUTORREPARACION_REAL = (
    "¿La primera falla en un nodo real de Cloud Run se reparará sola en menos de 2 minutos?",
    "Lo resuelve el controlador de infraestructura: segundos entre la falla inyectada y el primer "
    "sondeo sano después del reemplazo.",
    "simulacion",
    "autorreparacion_real",
)
SEEDS = {
    # Creencia contra evidencia, y el sistema negándose a responder.
    "oraculo": [KUBERNETES, PYTHON, DOLAR],
    # El mecanismo de agregación: información dispersa que ningún buscador tiene.
    "agregacion": [VIERNES, LLM, ROLLBACK],
    # Un ejemplo de cada tipo.
    "mixta": [PYTHON, DOLAR, VIERNES],
    # La nube autónoma: la sala apuesta sobre lo que harán los agentes.
    "nube": [COOPERACION, AUTORREPARACION, TOPOLOGIA, CREDULIDAD],
    # La nube autónoma actuando sobre Cloud Run de verdad (INFRA_MODE=real).
    "nube_real": [COOPERACION, TOPOLOGIA, AUTORREPARACION_REAL, CREDULIDAD],
    # Encuadre: dos titulares, la sala dividida al azar, y el oráculo puesto a prueba con ambos.
    # La pregunta de la sala no lleva titular: es el grupo de control del mecanismo.
    "encuadre": [PYTHON_ENCUADRADO, KUBERNETES_ENCUADRADO, VIERNES],
}


def seed(service: MarketService, seed_set: str) -> None:
    # Todos abren en 50 %: si el precio se mueve, lo movió la sala, no la casa.
    names = [n.strip() for n in seed_set.split("+")]
    unknown = [n for n in names if n not in SEEDS]
    if unknown:
        raise ValueError(f"SEED_SET desconocido: {', '.join(unknown)} (opciones: {', '.join(SEEDS)}; "
                         "se combinan con «+»)")
    for name in names:
        for question, criteria, kind, *extra in SEEDS[name]:
            predicate = next((x for x in extra if isinstance(x, str)), None)
            framing = next((x for x in extra if isinstance(x, Framing)), None)
            service.create(question, criteria, kind=kind, predicate=predicate, framing=framing)
