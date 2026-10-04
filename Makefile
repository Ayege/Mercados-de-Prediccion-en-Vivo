.PHONY: install test lint run docker

install:
	python -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt

test:
	.venv/bin/pytest -q

lint:
	.venv/bin/ruff check .

run:
	.venv/bin/uvicorn app.main:app --reload --port 8080

docker:
	docker build -t oraculo-api:dev .
