"""Generate feature audit figure."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts._common import parse_args, apply_paper_style, resolve_output_dir, ensure_data_or_fail
from src.figures.discovery import find_latest_feature_audit
from src.figures.loading import load_feature_audit

def main():
    args = parse_args("Generate feature audit figure")
    apply_paper_style()
    output_dir = resolve_output_dir()

    audit_dir = find_latest_feature_audit()
    ensure_data_or_fail(audit_dir, "Error: No feature audit results directory found.")

    audit_data = load_feature_audit(audit_dir)
    ensure_data_or_fail(audit_data, "Error: Could not load feature audit data.")

    from src.figures.features import plot_feature_audit
    plot_feature_audit(audit_data, output_dir)

if __name__ == "__main__":
    main()
