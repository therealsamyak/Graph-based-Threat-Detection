.PHONY: i pipeline feature feature_audit eval check lint

i:
	uv sync

pipeline:
	uv run main.py

feature feature_audit:
	uv run feature.py

eval:
	uv run eval.py

check lint:
	uvx ruff check --fix .

