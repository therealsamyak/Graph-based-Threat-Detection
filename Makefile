.PHONY: i pipeline clean

i:
	uv sync

pipeline:
	uv run python run_experiment.py

clean:
	rm -rf results/metrics.csv results/experiment_results.json results/figures/*.png results/cache/*.parquet
