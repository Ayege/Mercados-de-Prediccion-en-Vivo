.PHONY: install test lint seguridad lock diagramas run docker

install:
	python -m venv .venv && .venv/bin/pip install --require-hashes -r requirements.lock \
		&& .venv/bin/pip install -r requirements-dev.txt && .venv/bin/pre-commit install

test:
	.venv/bin/pytest -q

lint:
	.venv/bin/ruff check .

# Los mismos controles que el pre-commit y que cloudbuild.yaml, para correrlos a mano.
seguridad:
	.venv/bin/ruff check . --select S
	.venv/bin/pip-audit --require-hashes -r requirements.lock
	.venv/bin/pytest -q tests/security tests/test_architecture.py tests/test_docs.py
	.venv/bin/pre-commit run gitleaks --all-files

# Tras cambiar requirements.txt: regenera el lock con hashes para todas las plataformas.
lock:
	uv pip compile requirements.txt --universal --python-version 3.12 --generate-hashes -o requirements.lock

# Tras editar docs/*.mmd: copia los diagramas en docs/ARQUITECTURA.md y renderiza el de contexto.
diagramas:
	.venv/bin/python scripts/sincronizar_diagramas.py
	echo '{"executablePath": "$(CHROME)"}' > /tmp/puppeteer-oraculo.json
	PUPPETEER_SKIP_DOWNLOAD=1 npx -y @mermaid-js/mermaid-cli@11 -p /tmp/puppeteer-oraculo.json -b white -w 1800 \
		-i docs/c4-nivel1-contexto.mmd -o docs/c4-nivel1-contexto.png
	PUPPETEER_SKIP_DOWNLOAD=1 npx -y @mermaid-js/mermaid-cli@11 -p /tmp/puppeteer-oraculo.json -b white \
		-i docs/c4-nivel1-contexto.mmd -o docs/c4-nivel1-contexto.svg

CHROME ?= /Applications/Google Chrome.app/Contents/MacOS/Google Chrome

run:
	.venv/bin/uvicorn app.main:app --reload --port 8080

docker:
	docker build -t oraculo-api:dev .
