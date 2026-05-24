.PHONY: i pipeline feature feature_audit eval baselines check lint all

i:
	uv sync

pipeline:
	uv run main.py

feature feature_audit:
	uv run feature.py

eval:
	uv run eval.py

baselines:
	uv run baselines.py

check lint:
	uvx ruff check --fix .

all:
	uv run feature.py
	uv run main.py
	uv run eval.py
	git add -A
	git commit -m "results at $$(date +%Y-%m-%d_%H:%M:%S)"
	git push

