.PHONY: install run test lint

install:
	python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

run:
	.venv/bin/uvicorn app.main:app --reload

test:
	.venv/bin/pytest -q

lint:
	.venv/bin/python -m compileall -q app tests
