"""Summarize a JMeter CSV JTL into P50/P90/P95/P99/error metrics."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("jtl")
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    path = Path(args.jtl)
    rows = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                elapsed = float(row.get("elapsed", 0))
            except ValueError:
                continue
            rows.append((row.get("success", "").lower() == "true", elapsed))
    latencies = [elapsed for success, elapsed in rows if success]
    failures = len(rows) - len(latencies)
    result = {
        "file": str(path),
        "samples": len(rows),
        "success": len(latencies),
        "failures": failures,
        "error_rate_pct": round(failures / len(rows) * 100, 2) if rows else 0,
        "p50_ms": round(float(np.percentile(latencies, 50)), 2) if latencies else 0,
        "p90_ms": round(float(np.percentile(latencies, 90)), 2) if latencies else 0,
        "p95_ms": round(float(np.percentile(latencies, 95)), 2) if latencies else 0,
        "p99_ms": round(float(np.percentile(latencies, 99)), 2) if latencies else 0,
        "max_ms": round(max(latencies), 2) if latencies else 0,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.output:
        Path(args.output).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )


if __name__ == "__main__":
    main()
