"""POST /api/v1/face/detect: image validation, auth, idempotency, CORS."""

from __future__ import annotations

import uuid

import pytest

from tests.support import expect_error, expect_ok, image_file


def _detect(client, samples, data=None, *, headers=None, auth=True):
    return client.upload(
        "/api/v1/face/detect",
        files={"image": image_file(data or samples["face_a"])},
        headers=headers,
        auth=auth,
    )


def test_detect_png_success(client, samples):
    response = _detect(client, samples)
    data = expect_ok(response)
    assert data["face_count"] == 1
    assert data["width"] == 320 and data["height"] == 320
    bbox = data["faces"][0]["bbox"]
    assert bbox["width"] > 0 and bbox["height"] > 0
    assert data["provider"] == "iflytek"
    assert response.headers["X-Provider-Mode"] == "iflytek"
    assert float(response.headers["X-Process-Time-Ms"]) >= 0


def test_detect_jpeg_success(client, samples):
    response = client.upload(
        "/api/v1/face/detect",
        files={"image": image_file(samples["face_a_jpg"], "face.jpg", "image/jpeg")},
    )
    data = expect_ok(response)
    assert data["face_count"] == 1


def test_detect_missing_file(client):
    response = client.post("/api/v1/face/detect", files={}, data={})
    expect_error(response, status=400, code=40001)


def test_detect_empty_file(client):
    response = client.upload(
        "/api/v1/face/detect", files={"image": image_file(b"", "empty.png")}
    )
    expect_error(response, status=400, code=40002)


def test_detect_invalid_image_bytes(client, samples):
    response = client.upload(
        "/api/v1/face/detect",
        files={"image": image_file(samples["invalid"], "invalid.png", "image/png")},
    )
    expect_error(response, status=400, code=40003)


def test_detect_unsupported_gif(client, samples):
    response = client.upload(
        "/api/v1/face/detect",
        files={"image": image_file(samples["gif"], "sample.gif", "image/gif")},
    )
    expect_error(response, status=415, code=41500)


def test_detect_tiny_image(client, samples):
    response = client.upload(
        "/api/v1/face/detect",
        files={"image": image_file(samples["tiny"], "tiny.png")},
    )
    expect_error(response, status=422, code=42202)


def test_detect_oversized_image(client, samples):
    response = client.upload(
        "/api/v1/face/detect",
        files={"image": image_file(samples["oversized"], "large.png")},
    )
    expect_error(response, status=413, code=41300)


def test_detect_requires_api_key(client, samples):
    response = _detect(client, samples, auth=False)
    expect_error(response, status=401, code=40100)


def test_detect_rejects_wrong_api_key(client, samples):
    response = _detect(client, samples, headers={"X-API-Key": "wrong-key"})
    expect_error(response, status=401, code=40101)


def test_detect_duplicate_key_replays_without_provider_call(client, samples, provider_stats):
    key = f"detect-{uuid.uuid4().hex}"
    before = provider_stats()
    first = _detect(client, samples, headers={"Idempotency-Key": key})
    second = _detect(client, samples, headers={"Idempotency-Key": key})
    expect_ok(first)
    expect_ok(second)
    assert first.json()["data"]["faces"] == second.json()["data"]["faces"]
    assert second.headers["X-Idempotent-Replay"] == "true"
    after = provider_stats()
    assert after["detect"] - before["detect"] == 1


def test_detect_same_key_different_payload_conflicts(client, samples):
    key = f"detect-{uuid.uuid4().hex}"
    expect_ok(_detect(client, samples, headers={"Idempotency-Key": key}))
    response = _detect(
        client,
        samples,
        data=samples["face_b"],
        headers={"Idempotency-Key": key},
    )
    expect_error(response, status=409, code=40900)


def test_detect_cors_preflight_without_api_key(client):
    response = client.request(
        "OPTIONS",
        "/api/v1/face/detect",
        auth=False,
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-api-key, content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"
    assert "X-API-Key" in response.headers["Access-Control-Allow-Headers"]
    assert "POST" in response.headers["Access-Control-Allow-Methods"]
