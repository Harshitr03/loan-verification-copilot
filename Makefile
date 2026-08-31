.PHONY: install seed test fnma-demo

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

fnma-demo:
	$(PY) -c "from fnma_sf import build_demo_tape; print(build_demo_tape('2025Q1.csv', 'data/fnma_loan_tape.csv', 5000))"
