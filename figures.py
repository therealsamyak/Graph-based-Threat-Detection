"""Generate paper-quality figures from pipeline results."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from src.figures import apply_paper_style, discover_all, generate_all, load_all, parse_args

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

DEFAULT_OUTPUT_DIR = Path("figure_results") / datetime.now().strftime("%Y%m%d_%H%M%S")


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir) if args.output_dir != "figures" else DEFAULT_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    apply_paper_style()

    sources = discover_all(args.run_id)
    data = load_all(sources)
    generate_all(data, output_dir)


if __name__ == "__main__":
    main()
