"""Concurrency: parallel requests, same-key stampede and unique tracing."""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor

import requests

from tests.support import image_file


def _headers(key: str, idem: str | None = None):
    headers = {"X-API-Key": key, "Accept": "application/json"}
    if idem:
        headers["Idempotency-Key"] = idem
    return headers


def test_parallel_detect_has_no_500(face_server, samples):
    base = face_server["base_url"]

    def call(_):
        return requests.post(
            f"{base}/api/v1/face/detect",
            headers=_headers("test-service-key", f"par-{uuid.uuid4().hex}"),
            files={"image": image_file(samples["face_a"])},
            timeout=20,
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(call, range(16)))
    assert [r.status_code for r in responses] == [200] * 16
    assert {r.json()["data"]["face_count"] for r in responses} == {1}


def test_parallel_same_idempotency_key_only_calls_provider_once(
    face_server, samples, provider_stats
):
    base = face_server["base_url"]
    key = f"stampede-{uuid.uuid4().hex}"
    before = provider_stats()

    def call(_):
        return requests.post(
            f"{base}/api/v1/face/detect",
            headers=_headers("test-service-key", key),
            files={"image": image_file(samples["face_a"])},
            timeout=20,
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(call, range(8)))
    assert all(r.status_code == 200 for r in responses)
    replays = [r for r in responses if r.headers.get("X-Idempotent-Replay") == "true"]
    fresh = [r for r in responses if r.headers.get("X-Idempotent-Replay") != "true"]
    assert len(fresh) == 1
    assert len(replays) == 7
    assert {r.json()["data"]["faces"][0]["bbox"]["width"] for r in responses} == {
        responses[0].json()["data"]["faces"][0]["bbox"]["width"]
    }
    after = provider_stats()
    assert after["detect"] - before["detect"] == 1


def test_parallel_compare_returns_unique_request_ids(face_server, samples):
    base = face_server["base_url"]

    def call(_):
        return requests.post(
            f"{base}/api/v1/face/compare",
            headers=_headers("test-service-key", f"cmp-{uuid.uuid4().hex}"),
            files={
                "image_a": image_file(samples["face_a"], "a.png"),
                "image_b": image_file(samples["face_b"], "b.png"),
            },
            timeout=20,
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(call, range(8)))
    assert all(r.status_code == 200 for r in responses)
    request_ids = {r.json()["request_id"] for r in responses}
    assert len(request_ids) == 8


def test_idempotency_locks_are_reclaimed(face_server):
    manager = face_server["app"].extensions["idempotency"]
    for index in range(20):
        data, status, replay = manager.execute(
            f"lock-{uuid.uuid4().hex}-{index}",
            f"fingerprint-{index}",
            lambda: ({"ok": True}, 200),
        )
        assert data == {"ok": True} and status == 200 and replay is False
    assert manager._locks == {}

