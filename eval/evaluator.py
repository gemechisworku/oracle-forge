from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent.main import run_agent
from agent.utils import wilson_interval


class LocalEvaluator:
    def __init__(self, queries_path: Path) -> None:
        self.queries_path = queries_path
        self.queries = self._load_queries(queries_path)

    def _load_queries(self, path: Path) -> List[Dict[str, Any]]:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, dict):
            return payload.get("queries", [])
        if isinstance(payload, list):
            return payload
        return []

    def evaluate(self) -> Dict[str, Any]:
        results: List[Dict[str, Any]] = []
        correct = 0
        for query_case in self.queries:
            outcome = run_agent(
                question=query_case["question"],
                available_databases=query_case.get(
                    "available_databases",
                    ["postgresql", "mongodb", "sqlite", "duckdb"],
                ),
                schema_info=query_case.get("schema_info", {}),
            )
            is_correct = self._is_correct(query_case, outcome)
            correct += 1 if is_correct else 0
            results.append(
                {
                    "query_id": query_case["id"],
                    "question": query_case["question"],
                    "expected": query_case["expected"],
                    "answer": outcome.get("answer"),
                    "status": outcome.get("status"),
                    "confidence": outcome.get("confidence"),
                    "correct": is_correct,
                    "failure_type": None if is_correct else self._failure_type(query_case, outcome),
                    "trace": outcome.get("trace", []),
                    "used_databases": outcome.get("used_databases", []),
                }
            )
        total = len(results)
        pass_at_1 = (correct / total) if total else 0.0
        ci_low, ci_high = wilson_interval(correct, total)
        return {
            "total_queries": total,
            "correct_first_answers": correct,
            "pass@1": round(pass_at_1, 4),
            "confidence_interval_95": [round(ci_low, 4), round(ci_high, 4)],
            "results": results,
        }

    def _is_correct(self, query_case: Dict[str, Any], outcome: Dict[str, Any]) -> bool:
        expected = query_case.get("expected", {})
        actual = outcome.get("answer")
        if outcome.get("status") == "failure":
            return False
        expected_type = expected.get("type", "equals")
        expected_value = expected.get("value")
        if expected_type == "equals":
            return actual == expected_value
        if expected_type == "contains":
            return str(expected_value).lower() in str(actual).lower()
        if expected_type == "min":
            try:
                return float(actual) >= float(expected_value)
            except (TypeError, ValueError):
                return False
        return False

    def _failure_type(self, query_case: Dict[str, Any], outcome: Dict[str, Any]) -> str:
        required_dbs = set(query_case.get("required_databases", []))
        used_dbs = {entry.get("database") for entry in outcome.get("used_databases", [])}
        if required_dbs and not required_dbs.issubset(used_dbs):
            return "routing error"
        trace = outcome.get("trace", [])
        if any("join" in str(entry).lower() for entry in trace):
            return "join failure"
        question = query_case.get("question", "").lower()
        if "sentiment" in question or "extract" in question:
            return "extraction failure"
        return "reasoning failure"
