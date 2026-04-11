from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.dab_evaluator import DABEvaluator, append_score_log, compute_progression, run_probes, run_regression_suite


def main() -> None:
    eval_root = ROOT / "eval"
    dataset_path = eval_root / "dab_pg_mongo_queries.json"
    probes_path = eval_root / "adversarial_probes.json"
    regression_path = eval_root / "regression_queries.json"
    score_log_path = eval_root / "score_log.jsonl"

    trials_for_test = 3
    baseline = DABEvaluator(dataset_path=dataset_path, trials_per_query=trials_for_test).evaluate()
    append_score_log(score_log_path, "baseline", baseline)
    final = DABEvaluator(dataset_path=dataset_path, trials_per_query=trials_for_test).evaluate()
    append_score_log(score_log_path, "final", final)
    progression = compute_progression(score_log_path)
    regression = run_regression_suite(regression_path)
    probes = run_probes(probes_path)

    full_report = {
        "baseline": baseline,
        "final": final,
        "progression": progression,
        "regression": regression,
        "probes": probes,
    }
    (eval_root / "dab_results.json").write_text(json.dumps(full_report, indent=2, ensure_ascii=False), encoding="utf-8")
    (eval_root / "submission_results.json").write_text(
        json.dumps(
            {
                "team_name": "Oracle Forge",
                "benchmark": "DAB-like PG+Mongo",
                "pass@1": final["pass@1"],
                "confidence_interval": final["pass@1_ci95"],
                "trials_per_query": final["trials_per_query"],
                "total_queries": final["total_queries"],
                "connected_db_count": final["connected_db_count"],
                "active_db_types": final["active_db_types"],
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "pass@1": final["pass@1"],
                "connected_db_count": final["connected_db_count"],
                "active_db_types": final["active_db_types"],
                "probe_validity": probes["probe_validity"],
                "regression_pass": regression["regression_pass"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
