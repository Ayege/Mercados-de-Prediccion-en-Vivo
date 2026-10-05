"""La documentación de arquitectura no puede quedar vieja respecto de sus fuentes."""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_architecture_doc_matches_the_mmd_sources():
    result = subprocess.run([sys.executable, "scripts/sincronizar_diagramas.py", "--check"],  # noqa: S603
                            cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout


def test_every_diagram_source_is_shown_in_the_architecture_doc():
    doc = (ROOT / "docs" / "ARQUITECTURA.md").read_text()
    for mmd in (ROOT / "docs").glob("*.mmd"):
        assert f"<!-- mmd:{mmd.stem} -->" in doc, f"{mmd.name} no aparece en ARQUITECTURA.md"


def test_local_links_in_docs_point_to_existing_files():
    for md in [ROOT / "README.md", ROOT / "SECURITY.md", *(ROOT / "docs").glob("*.md")]:
        text = re.sub(r"```.*?```", "", md.read_text(), flags=re.S)  # sin bloques de código
        text = re.sub(r"`[^`]*`", "", text)  # ni código en línea
        for target in re.findall(r"\]\(([^)#]+?)\)", text):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            assert (md.parent / target).exists(), f"{md.name} enlaza a {target}, que no existe"
