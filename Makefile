PY := venv/Scripts/python.exe

.PHONY: check lint fmt fmt-check test hooks

check: lint fmt-check test

lint:
	$(PY) -m ruff check .

fmt:
	$(PY) -m ruff format .

fmt-check:
	$(PY) -m ruff format --check .

test:
	$(PY) -m pytest tests/ -q

hooks:
	$(PY) scripts/install_hooks.py
