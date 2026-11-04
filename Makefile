PY ?= python3

.PHONY: all install pipeline test lint site serve clean

## all: install, run the full pipeline, lint, test and build the site (the one command)
all: install pipeline lint test site

install:
	$(PY) -m pip install -q -e ".[dev]"

pipeline:
	$(PY) -m procontrol run

test:
	$(PY) -m pytest

lint:
	$(PY) -m ruff check src tests

site:
	$(PY) -m mkdocs build --strict

serve:
	$(PY) -m mkdocs serve

clean:
	rm -rf data/raw data/warehouse site .pytest_cache
