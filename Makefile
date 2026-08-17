PYTHON ?= python3
AGENT_DOCTOR = PYTHONPATH=src $(PYTHON) -m agent_doctor
REPORT_DIR ?= build/reports

.PHONY: help install-dev test typecheck compile spec audit check package

help:
	@echo "install-dev  Install editable package and development dependencies"
	@echo "test         Run unit and integration tests"
	@echo "typecheck    Run mypy over the runtime package"
	@echo "compile      Compile source and tests"
	@echo "spec         Validate and run Stage 04 suites"
	@echo "audit        Run the repository-only CI diagnostic"
	@echo "check        Run all deterministic source and contract gates"
	@echo "package      Build source and wheel distributions"

install-dev:
	$(PYTHON) -m pip install -e '.[dev]'

test:
	$(PYTHON) -m pytest

typecheck:
	$(PYTHON) -m mypy src/agent_doctor

compile:
	$(PYTHON) -m compileall -q src tests

spec:
	$(AGENT_DOCTOR) spec validate test-spec/fixtures/golden-v0.1.json
	$(AGENT_DOCTOR) spec validate test-spec/scenarios/stage-04-catalog-v0.1.json
	$(AGENT_DOCTOR) spec run test-spec/fixtures/golden-v0.1.json --repetitions 3 --summary
	$(AGENT_DOCTOR) spec run test-spec/scenarios/stage-04-catalog-v0.1.json --summary
	$(AGENT_DOCTOR) model spec --summary

audit:
	$(AGENT_DOCTOR) scan . --project-trust trusted --format ci --fail-on high --output $(REPORT_DIR)/agent-doctor-ci.json

check: test typecheck compile spec audit

package:
	$(PYTHON) -m build
