.PHONY: i pipeline feature feature_audit eval baselines check lint all test results

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

results: feature pipeline baselines eval
	@echo "Results regenerated in results/pipeline/, results/analysis/, results/baselines/, results/feature_audit/"

all:
	$(RM) -r .cache
	uv run feature.py
	uv run main.py
	uv run baselines.py
	uv run eval.py
	git add -A
	git commit -m "results at $$(date +%Y-%m-%d_%H:%M:%S)"
	git push

test:
	uv run feature.py --sample 10
	uv run main.py --sample 10
	uv run baselines.py
	$(RM) -r results
