.PHONY: i pipeline feature feature_audit check lint

i:
	uv sync

pipeline:
	uv run main.py

feature feature_audit:
	uv run feature.py

check lint:
	uvx ruff check --fix .

