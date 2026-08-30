.PHONY: install seed test

VENV := .venv
PY := $(VENV)/bin/python

$(VENV):
	python3 -m venv $(VENV)

install: $(VENV)
	$(PY) -m pip install -e ".[dev]"

seed:
	$(PY) -m data.generate --rows 5000 --seed 1234 --out-dir data

test:
	$(PY) -m pytest -q
