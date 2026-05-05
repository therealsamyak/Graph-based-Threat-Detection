.PHONY: i pipeline check

i:
	uv sync

pipeline:
	uv run python main.py

check:
	uvx ruff check --fix .

