.PHONY: setup install test eval eval-replay diff view unit clean

PY ?= python3

# Optional knobs. Usage:   make eval FILTER=refusal_confidential_hr REPEATS=3 CONCURRENCY=2 MAX_USD=2
FILTER ?=
REPEATS ?=
CONCURRENCY ?= 2
MAX_USD ?= 5.0

# Build the flag string from the knobs above.
EVAL_FLAGS = --cases cases/ --out reports/ --concurrency $(CONCURRENCY) --max-usd $(MAX_USD)
ifneq ($(FILTER),)
EVAL_FLAGS += --filter $(FILTER)
endif
ifneq ($(REPEATS),)
EVAL_FLAGS += --repeats $(REPEATS)
endif

setup:
	@test -d corpus || unzip -oq corpus.zip
	$(PY) -m pip install -r requirements.txt

install: setup

unit:
	$(PY) -m pytest tests/ -q

# End-to-end: run agent on every case, score, write HTML + JSON report.
# Needs ANTHROPIC_API_KEY.
eval:
	$(PY) -m drleval.cli run $(EVAL_FLAGS)

# Re-score committed fixture traces. Default is offline (hard assertions
# only, no judge calls) — fast and free for demos and graders without an
# API key. Set WITH_JUDGE=1 to re-run soft assertions through the judge.
WITH_JUDGE ?=
REPLAY_FLAGS = --traces fixtures/traces/ --cases cases/ --out reports/
ifeq ($(WITH_JUDGE),)
REPLAY_FLAGS += --no-judge
endif
eval-replay:
	$(PY) -m drleval.cli rescore $(REPLAY_FLAGS)

diff:
	$(PY) -m drleval.cli diff --current reports/latest.json --previous reports/previous.json

view:
	@echo "Open reports/latest.html in your browser."
	@command -v open >/dev/null && open reports/latest.html || true

# Default target used by graders: offline, fast, no API required.
test: unit

clean:
	rm -rf reports/ traces/ .pytest_cache/ **/__pycache__
