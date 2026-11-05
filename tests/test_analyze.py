"""POST /api/v1/face/analyze: attributes contract and upstream errors."""

from __future__ import annotations

import json
import uuid

from tests.support import expect_error, expect_ok, image_file


def _analyze(client, samples, *, attrs=None, data=None, headers=None, auth=True):
    form = {}
    if attrs is not None:
        form["attributes"] = json.dumps(attrs)
    return client.upload(
        "/api/v1/face/analyze",
        files={"image": image_file(data or samples["face_a"])},
        data=form,
        headers=headers,
        auth=auth,
    )


def test_analyze_default_attributes(client, samples):
    response = _analyze(client, samples)
    data = expect_ok(response)
    assert set(data["face"]) == {"age", "gender", "glasses", "mask"}
    assert data["face"]["age"] >= 18
    assert data["face"]["gender"] in {"male", "female"}
    assert isinstance(data["face"]["glasses"], bool)
    assert isinstance(data["face"]["mask"], bool)


def test_analyze_selected_attributes(client, samples):
    data = expect_ok(_analyze(client, samples, attrs=["age", "glasses"]))
    assert set(data["face"]) == {"age", "glasses"}
    assert data["attributes"] == ["age", "glasses"]


def test_analyze_missing_image(client):
    response = client.post("/api/v1/face/analyze", files={}, data={})
    expect_error(response, status=400, code=40001)


def test_analyze_malformed_attributes(client, samples):
    response = client.upload(
        "/api/v1/face/analyze",
        files={"image": image_file(samples["face_a"])},
        data={"attributes": "{not-json"},
    )
    expect_error(response, status=400, code=40005)


def test_analyze_attributes_not_list(client, samples):
    response = client.upload(
        "/api/v1/face/analyze",
        files={"image": image_file(samples["face_a"])},
        data={"attributes": json.dumps({"age": 20})},
    )
    expect_error(response, status=400, code=40005)


def test_analyze_unknown_attribute(client, samples):
    response = _analyze(client, samples, attrs=["age", "salary"])
    expect_error(response, status=400, code=40005)


def test_analyze_empty_file(client):
    response = client.upload(
        "/api/v1/face/analyze", files={"image": image_file(b"", "empty.png")}
    )
    expect_error(response, status=400, code=40002)


def test_analyze_oversized_image(client, samples):
    response = client.upload(
        "/api/v1/face/analyze",
        files={"image": image_file(samples["oversized"], "large.png")},
    )
    expect_error(response, status=413, code=41300)


def test_analyze_requires_api_key(client, samples):
    response = _analyze(client, samples, auth=False)
    expect_error(response, status=401, code=40100)


def test_analyze_duplicate_key_replays(client, samples, provider_stats):
    key = f"analyze-{uuid.uuid4().hex}"
    before = provider_stats()
    first = _analyze(client, samples, attrs=["age", "gender"], headers={"Idempotency-Key": key})
    second = _analyze(client, samples, attrs=["age", "gender"], headers={"Idempotency-Key": key})
    expect_ok(first)
    expect_ok(second)
    assert second.headers["X-Idempotent-Replay"] == "true"
    after = provider_stats()
    assert after["analyze"] - before["analyze"] == 1
