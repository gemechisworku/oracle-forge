#!/usr/bin/env python3
"""
test_probes.py - Automated Adversarial Probe Runner for Oracle Forge Agent

Runs 18 probes against the data agent and verifies correctness.

Usage:
    # Test a live agent via HTTP endpoint
    python test_probes.py --agent-url http://localhost:8000

    # Test the agent class directly (requires agent module on PYTHONPATH)
    python test_probes.py --direct

    # Run only specific probes by ID
    python test_probes.py --agent-url http://localhost:8000 --probes M1,I2,U3

Results are saved to test_results.json alongside this file.
"""

import asyncio
import json
import sys
import os
import re
import argparse
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

# Max probes executing simultaneously. Keeps the agent from being overwhelmed
# while still running the 18-probe suite in parallel.
_PROBE_CONCURRENCY = 5

# Agent query timeout in seconds (cross-DB joins can be slow).
_QUERY_TIMEOUT = 60.0

# -----------------------------------------------------------------------------
# Probe Definitions — must stay in sync with probes.md Quick Reference Table.
#
# Each entry: (id, category, query, expected_keywords)
#
# Keyword matching contract:
#   - Single-word keyword  → word-boundary match  (prevents 'high' → 'highway')
#   - Multi-word phrase    → case-insensitive substring match
# -----------------------------------------------------------------------------
PROBES: List[Tuple[str, str, str, List[str]]] = [
    # ── M: Multi-database (6 probes) ─────────────────────────────────────────
    (
        "M1", "M",
        "For each customer who opened a support ticket in MongoDB, show their "
        "total sales amount from PostgreSQL. Customer IDs in PostgreSQL are "
        "integers; in MongoDB they are strings like 'CUST_123'.",
        # Fixed: "CUST_" and "total_sales" are schema artifacts that never appear
        # in a natural-language response. Correct keywords validate the join result.
        ["total sales", "customer"],
    ),
    (
        "M2", "M",
        "Find products that were ordered in SQLite (order_date = 'YYYY-MM-DD') "
        "but had zero stock in DuckDB (inventory_date = 'MM/DD/YYYY') during "
        "the same calendar week.",
        ["week", "zero stock"],
    ),
    (
        "M3", "M",
        "From MongoDB product reviews (field 'review_text'), count how many "
        "contain the word 'defective'. Then join with PostgreSQL returns table "
        "to see which defective products were returned within 30 days.",
        ["defective", "returned"],
    ),
    (
        "M4", "M",
        "What is the average sentiment score (MongoDB `sentiment` field) for "
        "products that have sold more than 100 units in PostgreSQL?",
        # Fixed: "average sentiment" is a free-text phrase that may not appear
        # verbatim; "units" is out of spec. "sentiment" + "products" cover the
        # two concepts a correct response must express.
        ["sentiment", "products"],
    ),
    (
        "M5", "M",
        "For each user in MongoDB collection 'users', fetch their last login "
        "date from PostgreSQL table 'logins'.",
        ["last login", "user"],
    ),
    (
        "M6", "M",
        "Join SQLite table 'customers' (customer_id TEXT) with DuckDB table "
        "'loyalty' (cust_id INTEGER) using the first 5 characters of the TEXT "
        "id after stripping 'ID-'. Return name and points.",
        ["name", "points"],
    ),

    # ── I: Ill-formatted join keys (4 probes) ────────────────────────────────
    (
        "I1", "I",
        "Match customers from PostgreSQL (id = 12345) with CRM MongoDB "
        "(customer_ref = 'CUST-12345'). Show name and total tickets.",
        ["name", "tickets"],
    ),
    (
        "I2", "I",
        "SQLite products table has 'PRD_123_A', DuckDB inventory has "
        "'PRD-123-A'. Join them.",
        ["product", "inventory"],
    ),
    (
        "I3", "I",
        "PostgreSQL users table stores email as username. MongoDB activity log "
        "stores 'user' as the local part (before '@'). Join to count actions "
        "per user.",
        ["actions", "per user"],
    ),
    (
        "I4", "I",
        "Join SQLite 'supplier' table (supplier_name VARCHAR) with DuckDB "
        "'procurement' table (vendor_name TEXT) where names may have extra "
        "spaces or different case.",
        # Fixed: was ["supplier", "vendor"] — generic field names that appear in
        # any response, including wrong ones. probes.md specifies "Acme Corp",
        # a specific resolved name that validates the fuzzy match actually worked.
        ["Acme Corp"],
    ),

    # ── U: Unstructured text transformation (4 probes) ───────────────────────
    (
        "U1", "U",
        "From the 'notes' column in MongoDB (free text), find the total amount "
        "refunded in March 2026. Example note: 'Refunded $49.99 for order 8823'.",
        ["49.99", "refunded"],
    ),
    (
        "U2", "U",
        "Count tickets where severity is 'high' based on keywords: "
        "'urgent', 'critical', 'down', 'outage'.",
        ["high", "urgent"],
    ),
    (
        "U3", "U",
        "From product descriptions like 'Samsung TV 55\" black', "
        "count how many are black vs silver.",
        ["black", "silver"],
    ),
    (
        "U4", "U",
        "Classify churn reasons from 'feedback' column into "
        "'price', 'service', 'competitor', 'other'.",
        ["price", "service", "competitor"],
    ),

    # ── D: Domain knowledge (4 probes) ───────────────────────────────────────
    (
        "D1", "D",
        "What is the churn rate for Q1 2026? Churn is defined as customers "
        "who have not made a payment in the last 90 days.",
        ["churn rate", "90 days"],
    ),
    (
        "D2", "D",
        "Show total sales for FY2025 (July 2024 - June 2025).",
        ["FY2025", "sales"],
    ),
    (
        "D3", "D",
        "Count active accounts on March 31, 2026. "
        "Active means: status != 'closed' AND last_login > 2026-01-01.",
        # Fixed: was ["active accounts", "not closed"]. "not closed" is never
        # produced verbatim by any agent; probes.md specifies ["active accounts"].
        ["active accounts"],
    ),
    (
        "D4", "D",
        "What was the total revenue in Q3? Use the authoritative source.",
        ["revenue", "authoritative"],
    ),
]

# Category labels for the summary report
_CAT_LABELS: Dict[str, str] = {
    "M": "Multi-DB          ",
    "I": "Ill-Formatted Keys",
    "U": "Unstructured Text ",
    "D": "Domain Knowledge  ",
}


class ProbeTestRunner:
    """
    Adversarial probe runner for Oracle Forge.

    Supports two modes:
    1. HTTP   — POSTs queries to a live agent REST endpoint (/ask)
    2. Direct — imports DataAgent locally and calls answer() directly

    Probes run concurrently (bounded by _PROBE_CONCURRENCY). Each answer is
    checked against expected keywords using word-boundary matching for single
    words and substring matching for phrases.
    """

    def __init__(
        self,
        agent_url: Optional[str] = None,
        use_direct: bool = False,
    ) -> None:
        self.agent_url = agent_url
        self.use_direct = use_direct
        self.agent: Optional[Any] = None       # DataAgent instance (direct mode)
        self.session: Optional[Any] = None     # aiohttp.ClientSession (HTTP mode)

    # -------------------------------------------------------------------------
    # Initialisation
    # -------------------------------------------------------------------------
    async def init(self) -> None:
        """Set up HTTP session or import and initialise the agent."""
        if self.use_direct:
            try:
                from agent.core.agent import DataAgent  # type: ignore[import]
                self.agent = DataAgent()
                assert self.agent is not None
                await self.agent.init()
                print("[Direct mode] Agent initialised successfully.")
            except ImportError as exc:
                print(f"ERROR: Could not import DataAgent: {exc}")
                print(
                    "Expected layout: agent/core/agent.py  →  class DataAgent\n"
                    "Ensure the agent package is on PYTHONPATH, or use --agent-url."
                )
                sys.exit(1)

        elif self.agent_url:
            try:
                import aiohttp
                self.session = aiohttp.ClientSession()
                async with self.session.get(
                    f"{self.agent_url}/health",
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status != 200:
                        # Hard abort — running 18 probes against a down agent
                        # produces 18 misleading failures instead of one clear message.
                        print(
                            f"ERROR: Agent health check returned HTTP {resp.status}. "
                            f"Is the agent running at {self.agent_url}?"
                        )
                        await self.session.close()
                        sys.exit(1)
                print(f"[HTTP mode] Agent reachable at {self.agent_url}")
            except ImportError:
                print("ERROR: aiohttp not installed. Run: pip install aiohttp")
                sys.exit(1)
            except Exception as exc:
                print(f"ERROR: Could not reach agent at {self.agent_url}: {exc}")
                sys.exit(1)
        else:
            print("ERROR: Must specify --agent-url or --direct")
            sys.exit(1)

    async def close(self) -> None:
        """Release HTTP session."""
        if self.session:
            await self.session.close()

    # -------------------------------------------------------------------------
    # Keyword matching
    # -------------------------------------------------------------------------
    @staticmethod
    def _keyword_found(keyword: str, text: str) -> bool:
        """
        Case-insensitive match with anti-false-positive guard.

        Single-word keyword  → word-boundary regex  (\bkeyword\b)
            Prevents 'high' matching 'highway', 'actions' matching 'transactions'.
        Multi-word phrase    → plain substring match
            'total sales', 'active accounts', 'churn rate', etc.
        """
        if " " in keyword:
            return keyword.lower() in text.lower()
        return bool(re.search(r"\b" + re.escape(keyword) + r"\b", text, re.IGNORECASE))

    # -------------------------------------------------------------------------
    # Query dispatch
    # -------------------------------------------------------------------------
    async def ask_agent(self, query: str) -> Tuple[str, Optional[Dict[str, Any]]]:
        """
        Send one query to the agent. Returns (answer_text, trace_dict | None).

        Both modes enforce _QUERY_TIMEOUT. Direct mode previously had no timeout,
        which would hang the entire suite on a stalled multi-DB query.
        """
        if self.use_direct:
            assert self.agent is not None, "agent not initialised — call init() first"
            result: Dict[str, Any] = await asyncio.wait_for(
                self.agent.answer(query), timeout=_QUERY_TIMEOUT
            )
            return result.get("answer", ""), result.get("trace")

        if self.agent_url:
            assert self.session is not None, "session not initialised — call init() first"
            import aiohttp
            async with self.session.post(
                f"{self.agent_url}/ask",
                json={"question": query},
                timeout=aiohttp.ClientTimeout(total=_QUERY_TIMEOUT),
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    return f"HTTP Error {resp.status}: {error_text}", None
                data = await resp.json()
                return data.get("answer", ""), data.get("trace")

        raise RuntimeError("No agent connection configured")

    # -------------------------------------------------------------------------
    # Single probe execution
    # -------------------------------------------------------------------------
    async def run_single_probe(
        self,
        probe_id: str,
        query: str,
        expected_keywords: List[str],
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Execute one probe. Returns (passed, message, trace).
        """
        try:
            answer, trace = await self.ask_agent(query)
            missing = [
                kw for kw in expected_keywords
                if not self._keyword_found(kw, answer)
            ]
            if not missing:
                return True, "All keywords found", trace
            return False, f"Missing keywords: {missing}", trace

        except asyncio.TimeoutError:
            return False, f"[{probe_id}] Timeout: no response within {_QUERY_TIMEOUT:.0f}s", None
        except Exception as exc:
            return False, f"[{probe_id}] Exception: {str(exc)[:150]}", None

    # -------------------------------------------------------------------------
    # Orchestration
    # -------------------------------------------------------------------------
    async def run_all(self, probe_filter: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Run all probes concurrently and return a results dictionary.

        Probes execute in parallel up to _PROBE_CONCURRENCY at a time.
        Output is printed as each probe completes; the final summary is
        presented in original probe order.
        """
        probes_to_run = PROBES
        if probe_filter:
            filter_set = set(probe_filter)
            probes_to_run = [p for p in PROBES if p[0] in filter_set]

        total = len(probes_to_run)
        # Map probe ID → original index so we can restore order after gather
        order = {pid: i for i, (pid, *_) in enumerate(probes_to_run)}

        print(f"\n{'='*60}")
        print(f"Running {total} adversarial probes  (concurrency={_PROBE_CONCURRENCY})")
        if probe_filter:
            print(f"Filter: {', '.join(probe_filter)}")
        print(f"{'='*60}\n")

        semaphore = asyncio.Semaphore(_PROBE_CONCURRENCY)

        async def _run(pid: str, cat: str, query: str, keywords: List[str]) -> Dict[str, Any]:
            async with semaphore:
                passed, message, trace = await self.run_single_probe(pid, query, keywords)
            status_str = "✅ PASS" if passed else f"❌ FAIL – {message}"
            print(f"  [{pid}] [{cat}] {status_str}")
            return {
                "id": pid,
                "category": cat,
                "query": query[:200],
                "expected_keywords": keywords,
                "passed": passed,
                "message": message,
                # json.dumps preserves structure; str(dict) produces unparseable output
                "trace_snippet": (
                    json.dumps(trace, default=str)[:300] if trace else None
                ),
                "timestamp": datetime.now().isoformat(),
            }

        raw: List[Dict[str, Any]] = await asyncio.gather(*[
            _run(pid, cat, query, kws)
            for pid, cat, query, kws in probes_to_run
        ])

        # Restore original probe order for the report
        results: List[Dict[str, Any]] = sorted(raw, key=lambda r: order[r["id"]])
        passed_count = sum(1 for r in results if r["passed"])

        # ── Overall summary ────────────────────────────────────────────────
        pass_rate = (passed_count / total * 100) if total else 0.0
        print(f"\n{'='*60}")
        print("SUMMARY")
        print(f"{'='*60}")
        print(f"Passed : {passed_count}/{total}")
        print(f"Failed : {total - passed_count}/{total}")
        print(f"Pass % : {pass_rate:.1f}%")

        # ── Per-category breakdown ─────────────────────────────────────────
        cat_stats: Dict[str, Dict[str, Any]] = {}
        for r in results:
            cat = r["category"]
            if cat not in cat_stats:
                cat_stats[cat] = {"passed": 0, "total": 0}
            cat_stats[cat]["total"] += 1
            if r["passed"]:
                cat_stats[cat]["passed"] += 1

        print("\nCategory Breakdown:")
        for cat in ["M", "I", "U", "D"]:
            if cat not in cat_stats:
                continue
            s = cat_stats[cat]
            rate = (s["passed"] / s["total"]) * 100
            bar = "█" * s["passed"] + "░" * (s["total"] - s["passed"])
            print(f"  {_CAT_LABELS[cat]}: {s['passed']}/{s['total']}  ({rate:5.1f}%)  [{bar}]")

        # ── Persist to file (path anchored to script location, not CWD) ───
        output = {
            "timestamp": datetime.now().isoformat(),
            "mode": "direct" if self.use_direct else f"http:{self.agent_url}",
            "total_probes": total,
            "passed": passed_count,
            "failed": total - passed_count,
            "pass_rate": pass_rate,
            "category_breakdown": {
                cat: {
                    "passed": cat_stats[cat]["passed"],
                    "total": cat_stats[cat]["total"],
                    "pass_rate": (
                        cat_stats[cat]["passed"] / cat_stats[cat]["total"] * 100
                    ),
                }
                for cat in cat_stats
            },
            "results": results,
        }

        output_file = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "test_results.json"
        )
        with open(output_file, "w") as fh:
            json.dump(output, fh, indent=2)
        print(f"\nDetailed results saved to: {output_file}")

        return output


# -----------------------------------------------------------------------------
# Entry point
# -----------------------------------------------------------------------------
async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run adversarial probes against Oracle Forge agent"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--agent-url",
        type=str,
        help="Base URL of live agent (e.g., http://localhost:8000)",
    )
    group.add_argument(
        "--direct",
        action="store_true",
        help="Import DataAgent directly (requires agent package on PYTHONPATH)",
    )
    parser.add_argument(
        "--probes",
        type=str,
        help="Comma-separated probe IDs to run (e.g., M1,I2,U3). Default: all",
    )

    args = parser.parse_args()

    probe_filter: Optional[List[str]] = None
    if args.probes:
        probe_filter = [p.strip() for p in args.probes.split(",")]

    runner = ProbeTestRunner(agent_url=args.agent_url, use_direct=args.direct)
    try:
        await runner.init()
        output = await runner.run_all(probe_filter=probe_filter)
        sys.exit(1 if output["failed"] > 0 else 0)
    finally:
        await runner.close()


if __name__ == "__main__":
    asyncio.run(main())
