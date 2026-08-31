.PHONY: install seed test test-all fnma-demo up down logs seed-db samples

VENV := .venv
PY := $(VENV)/bin/python

$(VENV):
	python3 -m venv $(VENV)

install: $(VENV)
	$(PY) -m pip install -e ".[backend,test,dev]"

seed:
	$(PY) -m data.generate --rows 5000 --seed 1234 --out-dir data

test:
	$(PY) -m pytest -q

# full suite: python (unit + integration if LVC_TEST_MONGODB_URI set) + frontend typecheck/build
test-all:
	$(PY) -m pytest -q
	cd frontend && npm run build

fnma-demo:
	$(PY) -c "from fnma_sf import build_demo_tape; print(build_demo_tape('2025Q1.csv', 'data/fnma_loan_tape.csv', 5000))"

# --- Docker (one-command run) ---------------------------------------------
up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f api

# regenerate the synthetic package, then restart api so its lifespan re-seeds users
seed-db: seed
	docker compose restart api

# regenerate the committed sample verified-output + audit export (needs a local mongo)
samples:
	LVC_TEST_MONGODB_URI=$${LVC_TEST_MONGODB_URI:-mongodb://localhost:27017} $(PY) scripts/make_samples.py
