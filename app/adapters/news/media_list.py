"""Carga la lista de medios que define el ponente (MEDIOS_ARCHIVO)."""
from __future__ import annotations

import json
from pathlib import Path

from ...domain.media import MediaList, Outlet


def load(path: str | Path) -> MediaList:
    """Un archivo ausente es una lista vacía: las preguntas desde noticias quedan apagadas."""
    p = Path(path)
    if not p.exists():
        return MediaList()
    data = json.loads(p.read_text(encoding="utf-8"))
    outlets = tuple(Outlet(m["nombre"], m["dominio"].lower().removeprefix("www."), m["inclinacion"],
                           m["fuente"]) for m in data.get("medios", []))
    return MediaList(outlets, source=str(data.get("fuente", "")))
