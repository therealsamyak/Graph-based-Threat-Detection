.PHONY: i pipeline check lint

i:
	uv sync

pipeline:
	uv run python main.py

check lint:
	uvx ruff check --fix .

