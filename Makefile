.PHONY: all install test run clean

PYTHON = python
PYTEST = pytest

all: install run test

install:
	$(PYTHON) -m pip install -r requirements.txt

run:
	$(PYTHON) src/data_loader.py
	$(PYTHON) src/dcf_engine.py
	$(PYTHON) src/comps_engine.py
	$(PYTHON) src/excel_generator.py

test:
	$(PYTEST) -v

clean:
	rm -rf __pycache__ .pytest_cache
