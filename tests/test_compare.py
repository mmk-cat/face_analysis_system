"""POST /api/v1/face/compare: similarity, validation, idempotency, CORS."""

from __future__ import annotations

import uuid

from tests.support import expect_error, expect_ok, image_file


def _compare(client, samples, *, a=None, b=None, headers=None, auth=True):
    files = {}
    if a is not False:
        files["image_a"] = image_file(a if a is not None else samples["face_a"], "a.png")
    if b is not False:
        files["image_b"] = image_file(b if b is not None else samples["face_a"], "b.png")
    return client.upload("/api/v1/face/compare", files=files, headers=headers, auth=auth)


def test_compare_same_image(client, samples):
    data = expect_ok(_compare(client, samples))
    assert data["same_person"] is True
    assert data["similarity"] >= 0.95
    assert data["threshold"] == 0.75
    assert data["provider"] == "iflytek"


def test_compare_different_images(client, samples):
    data = expect_ok(_compare(client, samples, b=samples["face_b"]))
    assert data["same_person"] is False
    assert data["similarity"] < 0.75


def test_compare_missing_image_a(client, samples):
    response = _compare(client, samples, a=False)
    expect_error(response, status=400, code=40001)


def test_compare_missing_image_b(client, samples):
    response = _compare(client, samples, b=False)
    expect_error(response, status=400, code=40001)


def test_compare_empty_image_b(client, samples):
    response = _compare(client, samples, b=b"")
    expect_error(response, status=400, code=40002)


def test_compare_invalid_image_a(client, samples):
    response = _compare(client, samples, a=samples["invalid"])
    expect_error(response, status=400, code=40003)


def test_compare_oversized_image_a(client, samples):
    response = _compare(client, samples, a=samples["oversized"])
    expect_error(response, status=413, code=41300)


def test_compare_requires_api_key(client, samples):
    response = _compare(client, samples, auth=False)
    expect_error(response, status=401, code=40100)


def test_compare_duplicate_key(client, samples, provider_stats):
    key = f"compare-{uuid.uuid4().hex}"
    before = provider_stats()
    first = _compare(
        client, samples, b=samples["face_b"], headers={"Idempotency-Key": key}
    )
    second = _compare(
        client, samples, b=samples["face_b"], headers={"Idempotency-Key": key}
    )
    data1 = expect_ok(first)
    data2 = expect_ok(second)
    assert data1["similarity"] == data2["similarity"]
    assert second.headers["X-Idempotent-Replay"] == "true"
    assert provider_stats()["compare"] - before["compare"] == 1


def test_compare_same_key_different_payload(client, samples):
    key = f"compare-{uuid.uuid4().hex}"
    expect_ok(_compare(client, samples, headers={"Idempotency-Key": key}))
    response = _compare(
        client, samples, b=samples["face_b"], headers={"Idempotency-Key": key}
    )
    expect_error(response, status=409, code=40900)


def test_compare_cors_header_on_success(client, samples):
    response = _compare(
        client,
        samples,
        headers={"Origin": "http://localhost:3000"},
    )
    expect_ok(response)
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"
