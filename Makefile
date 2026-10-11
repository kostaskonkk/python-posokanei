.PHONY: models drift lint format type test live check

SPEC := spec/openapi.yaml
MODELS := src/posokanei/models.py

# The models are generated from the spec and committed. Never edit them by hand.
models:
	datamodel-codegen --input $(SPEC) --input-file-type openapi --output $(MODELS) \
		--output-model-type pydantic_v2.BaseModel --target-python-version 3.10 \
		--use-annotated --use-standard-collections --use-union-operator --field-constraints \
		--extra-fields allow --use-schema-description --disable-timestamp \
		--output-datetime-class datetime --formatters ruff-check ruff-format

drift: models
	git diff --exit-code -- $(MODELS)

lint:
	ruff check .
	ruff format --check .

format:
	ruff check --fix .
	ruff format .

type:
	mypy

test:
	pytest --cov --cov-report=term-missing

# Calls the real API. Add ARGS=--record to write the responses to tests/fixtures/.
live:
	pytest -m live $(ARGS)

check: lint type test
