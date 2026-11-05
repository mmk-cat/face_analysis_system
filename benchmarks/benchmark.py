"""Concurrency benchmark: unoptimized baseline vs optimized face API.

Usage:
    python benchmarks/benchmark.py --latency-ms 500 --requests 100 --concurrency 50
"""

from __future__ import annotations

import argparse
import json
import statistics
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
import requests
from werkzeug.serving import make_server

from app import create_app
from app.config import Settings
from benchmarks.baseline_server import create_app as create_baseline_app
from mock_iflytek.app import create_app as create_mock_app

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
SAMPLES = ROOT / "data" / "samples"


def _start(app):
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, f"http://127.0.0.1:{server.server_port}"


def _post_compare(base_url: str, image_a: bytes, image_b: bytes, *, api_key: str | None, idem: str | None):
    headers = {}
    if api_key:
        headers["X-API-Key"] = api_key
    if idem:
        headers["Idempotency-Key"] = idem
    started = time.perf_counter()
    try:
        response = requests.post(
            f"{base_url}/api/v1/face/compare",
            headers=headers,
            files={
                "image_a": ("a.png", image_a, "image/png"),
                "image_b": ("b.png", image_b, "image/png"),
            },
            timeout=40,
        )
        return response.status_code, (time.perf_counter() - started) * 1000
    except requests.RequestException:
        return 0, (time.perf_counter() - started) * 1000


def _percentile(values: list[float], q: float) -> float:
    return round(float(np.percentile(values, q)), 2) if values else 0.0


def _run_batch(
    name: str,
    base_url: str,
    *,
    api_key: str | None,
    image_a: bytes,
    image_b: bytes,
    requests_count: int,
    concurrency: int,
    same_key: bool,
) -> dict[str, Any]:
    fixed_key = f"bench-{name}-{uuid.uuid4().hex}" if same_key else None

    def one(index: int):
        idem = fixed_key or f"bench-{name}-{uuid.uuid4().hex}"
        return _post_compare(
            base_url, image_a, image_b, api_key=api_key, idem=idem
        )

    # Warmup is intentionally excluded from metrics.
    for _ in range(min(3, requests_count)):
        one(-1)
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        results = list(pool.map(one, range(requests_count)))
    wall = time.perf_counter() - started
    latencies = [latency for status, latency in results if status == 200]
    errors = sum(1 for status, _ in results if status != 200)
    return {
        "scenario": name,
        "requests": requests_count,
        "concurrency": concurrency,
        "same_idempotency_key": same_key,
        "success": len(latencies),
        "errors": errors,
        "wall_seconds": round(wall, 3),
        "throughput_rps": round(len(latencies) / wall, 2) if wall else 0,
        "p50_ms": _percentile(latencies, 50),
        "p90_ms": _percentile(latencies, 90),
        "p95_ms": _percentile(latencies, 95),
        "p99_ms": _percentile(latencies, 99),
        "mean_ms": round(statistics.mean(latencies), 2) if latencies else 0,
        "max_ms": round(max(latencies), 2) if latencies else 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--latency-ms", type=int, default=500)
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, nargs="+", default=[50, 100])
    args = parser.parse_args()

    image_a = (SAMPLES / "face_a.png").read_bytes()
    image_b = (SAMPLES / "face_a.png").read_bytes()
    mock_app = create_mock_app(
        app_id="bench-app", api_key="bench-key", latency_ms=args.latency_ms
    )
    mock_server, mock_thread, mock_url = _start(mock_app)

    baseline_app = create_baseline_app(
        mock_url, app_id="bench-app", api_key="bench-key"
    )
    baseline_server, baseline_thread, baseline_url = _start(baseline_app)

    optimized_settings = Settings(
        app_env="bench",
        api_key="bench-service-key",
        provider_mode="iflytek",
        iflytek_base_url=mock_url,
        iflytek_app_id="bench-app",
        iflytek_api_key="bench-key",
        db_path=REPORTS / "benchmark_face.db",
        max_image_bytes=4 * 1024 * 1024,
        provider_timeout=10,
    )
    optimized_app = create_app(optimized_settings)
    optimized_server, optimized_thread, optimized_url = _start(optimized_app)

    results = []
    try:
        for concurrency in args.concurrency:
            # Cold path: each request has a unique idempotency key.
            results.append(
                _run_batch(
                    f"cold-c{concurrency}",
                    baseline_url,
                    api_key=None,
                    image_a=image_a,
                    image_b=image_b,
                    requests_count=args.requests,
                    concurrency=concurrency,
                    same_key=False,
                )
            )
            results.append(
                _run_batch(
                    f"optimized-c{concurrency}",
                    optimized_url,
                    api_key="bench-service-key",
                    image_a=image_a,
                    image_b=image_b,
                    requests_count=args.requests,
                    concurrency=concurrency,
                    same_key=False,
                )
            )
            # Retry-storm path: all clients send the same idempotency key.
            results.append(
                _run_batch(
                    f"baseline-retry-c{concurrency}",
                    baseline_url,
                    api_key=None,
                    image_a=image_a,
                    image_b=image_b,
                    requests_count=args.requests,
                    concurrency=concurrency,
                    same_key=True,
                )
            )
            results.append(
                _run_batch(
                    f"optimized-retry-c{concurrency}",
                    optimized_url,
                    api_key="bench-service-key",
                    image_a=image_a,
                    image_b=image_b,
                    requests_count=args.requests,
                    concurrency=concurrency,
                    same_key=True,
                )
            )
    finally:
        for server in (optimized_server, baseline_server, mock_server):
            server.shutdown()
        for thread in (optimized_thread, baseline_thread, mock_thread):
            thread.join(timeout=5)

    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "provider_latency_ms": args.latency_ms,
        "requests_per_scenario": args.requests,
        "notes": (
            "baseline: 3 serial upstream calls, new connection per call; "
            "optimized: one compare call, pooled Session, timeout/retry + idempotency"
        ),
        "results": results,
    }
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "benchmark.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    lines = [
        "# 并发压测结果",
        "",
        f"- 上游模拟延迟：{args.latency_ms} ms/次",
        f"- 每个场景请求数：{args.requests}",
        "- baseline：逐图 detect ×2 + compare，共 3 次上游调用，每次新建连接",
        "- optimized：一次 face_compare + 连接池 + 超时/重试 + Idempotency-Key",
        "",
        "| 场景 | 并发 | 成功率 | 错误 | 吞吐(req/s) | P50 | P95 | P99 | 最大 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in results:
        lines.append(
            f"| {item['scenario']} | {item['concurrency']} | {item['success']}/{item['requests']} | "
            f"{item['errors']} | {item['throughput_rps']} | {item['p50_ms']} | "
            f"{item['p95_ms']} | {item['p99_ms']} | {item['max_ms']} |"
        )
    (REPORTS / "benchmark.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
