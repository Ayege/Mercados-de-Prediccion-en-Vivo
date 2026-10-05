"""Copia los diagramas de docs/*.mmd dentro de docs/ARQUITECTURA.md.

Los .mmd son la fuente de verdad. ARQUITECTURA.md los muestra en bloques ```mermaid
(GitHub los renderiza) entre marcadores <!-- mmd:NOMBRE --> ... <!-- /mmd -->.
tests/test_docs.py falla si alguien edita un .mmd sin correr este script.

    python scripts/sincronizar_diagramas.py           # reescribe ARQUITECTURA.md
    python scripts/sincronizar_diagramas.py --check   # solo verifica (sale con 1 si hay diferencias)

El render del diagrama de contexto (SVG y PNG) se regenera aparte; ver ARQUITECTURA.md.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

DOCS = Path(__file__).resolve().parents[1] / "docs"
DOC = DOCS / "ARQUITECTURA.md"
BLOCK = re.compile(r"(<!-- mmd:(?P<name>[\w-]+) -->\n)```mermaid\n.*?```\n(<!-- /mmd -->)", re.S)


def synced(text: str) -> str:
    def fill(m: re.Match) -> str:
        source = (DOCS / f"{m['name']}.mmd").read_text().rstrip("\n")
        return f"{m.group(1)}```mermaid\n{source}\n```\n{m.group(3)}"

    return BLOCK.sub(fill, text)


def main() -> int:
    current = DOC.read_text()
    expected = synced(current)
    if "--check" in sys.argv:
        if current != expected:
            print("docs/ARQUITECTURA.md no coincide con docs/*.mmd: corre scripts/sincronizar_diagramas.py")
            return 1
        return 0
    DOC.write_text(expected)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
