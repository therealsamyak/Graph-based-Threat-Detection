"""Common utilities for scripts."""

import argparse
import sys
from pathlib import Path

from src.figures.style import apply_paper_style as _apply_paper_style


def apply_paper_style() -> None:
    """Apply paper style from figures module."""
    _apply_paper_style()


def parse_args(description: str) -> argparse.Namespace:
    """Parse common script arguments.

    Args:
        description: Script description for help text.

    Returns:
        Parsed arguments with --run-id (optional).
    """
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="Pin to a specific results directory run (e.g., results/<run-id>/)",
    )
    return parser.parse_args()


def resolve_output_dir() -> Path:
    """Resolve output directory for figures.

    Returns:
        Path to figures directory, created if missing.
    """
    output_dir = Path("figures")
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def ensure_data_or_fail(data: object | None, message: str) -> object:
    """Ensure data is not None; exit with error if it is.

    Args:
        data: Data to check.
        message: Error message to print on failure.

    Returns:
        The data if not None.

    Raises:
        SystemExit: If data is None.
    """
    if data is None:
        print(message, file=sys.stderr)
        sys.exit(1)
    return data