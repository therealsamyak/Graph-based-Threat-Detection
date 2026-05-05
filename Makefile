.PHONY: i pipeline clean

i:
	uv sync

pipeline:
	uv run python main.py

clean:
	rm -rf results/metrics.csv results/experiment_results.json results/figures/*.png results/cache/*.parquet
