"""Texto de terceros dentro de un prompt.

Todo lo que no escribió el código (preguntas, titulares, nombres de medios,
temas) se escapa antes de ir entre etiquetas como <titular>…</titular>: así un
titular que contenga «</titular>» no puede cerrar la etiqueta y colar
instrucciones fuera de ella.
"""
from __future__ import annotations

import html


def dato(text: str) -> str:
    return html.escape(str(text), quote=True)
