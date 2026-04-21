.PHONY: setup install test eval eval-replay diff view unit clean

PY ?= python3

setup:
	@test -d corpus || unzip -oq corpus.zip
	$(PY) -m pip install -r requirements.txt

install: setup

unit:
	$(PY) -m pytest tests/ -q

# End-to-end: run agent on every case, score, write HTML + JSON report.
# Needs ANTHROPIC_API_KEY. Honors CASES=glob, CONCURRENCY=N, REPEATS=N.
eval:
	$(PY) -m drleval.cli run --cases cases/ --out reports/

# Re-score committed fixture traces without calling the agent (judge still runs).
eval-replay:
	$(PY) -m drleval.cli rescore --traces fixtures/traces/ --cases cases/ --out reports/

diff:
	$(PY) -m drleval.cli diff --current reports/latest.json --previous reports/previous.json

view:
	@echo "Open reports/latest.html in your browser."
	@command -v open >/dev/null && open reports/latest.html || true

# Default target used by graders: offline, fast, no API required.
test: unit

clean:
	rm -rf reports/ traces/ .pytest_cache/ **/__pycache__
