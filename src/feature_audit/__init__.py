"""Feature audit package."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from src.feature_audit.types import AuditConfig, AuditReport


def run_audit(
    run_dir: Path,
    output_dir: Path,
    config: AuditConfig | None = None,
) -> AuditReport:
    from src.feature_audit.loader import detect_duplicates, load_features
    from src.feature_audit.reporter import generate_report, save_report
    from src.feature_audit.scorer import (
        compute_feature_aucs,
        evaluate_selected,
        mark_duplicates,
        select_features,
        stratified_split,
    )

    cfg = config or AuditConfig()
    X, y, columns = load_features(run_dir)
    duplicate_pairs = detect_duplicates(X, columns, cfg.duplicate_threshold)
    cal_idx, eval_idx = stratified_split(X, y, cfg.holdout_frac, cfg.random_seed)
    results = compute_feature_aucs(X[cal_idx], y[cal_idx], columns, cfg.log1p_features)
    results = mark_duplicates(results, duplicate_pairs)
    selected = select_features(results, cfg.min_auc)
    selected_set = set(selected)
    results = [replace(result, selected=result.feature in selected_set) for result in results]
    report = AuditReport(
        features=results,
        selected_features=selected,
        calibration_n=len(cal_idx),
        eval_n=len(eval_idx),
        redteam_calibration=int(y[cal_idx].sum()),
        redteam_eval=int(y[eval_idx].sum()),
        config=cfg,
        duplicate_pairs=duplicate_pairs,
        eval_metrics=evaluate_selected(
            X, y, cal_idx, eval_idx, columns, selected, cfg.log1p_features
        ),
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown = generate_report(report)
    (output_dir / "feature_audit_results.json").write_text(json.dumps(report.to_dict(), indent=2))
    save_report(markdown, output_dir / "Feature_Audit_Results.md")
    return report


__all__ = ["AuditConfig", "AuditReport", "run_audit"]
