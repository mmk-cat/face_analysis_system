"""Persistence-level checks for gallery and idempotency records."""

from __future__ import annotations

import hashlib
import uuid

from tests.support import expect_error, expect_ok, image_file


def _register(client, samples, group_id, person_id):
    return client.upload(
        "/api/v1/face/register",
        files={"image": image_file(samples["face_a"])},
        data={"group_id": group_id, "person_id": person_id, "name": "DB Check"},
    )


def test_register_persists_gallery_image(client, samples, group_id, face_server):
    expect_ok(_register(client, samples, group_id, "P300"), 201)
    repository = face_server["app"].extensions["repository"]
    row = repository.get_person(group_id, "P300")
    assert row is not None
    assert bytes(row["image_bytes"]) == samples["face_a"]
    assert row["image_sha256"] == hashlib.sha256(samples["face_a"]).hexdigest()
    assert row["name"] == "DB Check"


def test_idempotency_record_persisted(client, samples, face_server):
    key = f"db-idem-{uuid.uuid4().hex}"
    response = client.upload(
        "/api/v1/face/detect",
        files={"image": image_file(samples["face_a"])},
        headers={"Idempotency-Key": key},
    )
    expect_ok(response)
    repository = face_server["app"].extensions["repository"]
    row = repository.get_idempotency(key)
    assert row is not None
    assert row["status"] == 200
    assert len(row["fingerprint"]) == 64
    assert "face_count" in row["data_json"]


def test_duplicate_person_keeps_one_row(client, samples, group_id, face_server):
    expect_ok(_register(client, samples, group_id, "P301"), 201)
    response = _register(client, samples, group_id, "P301")
    expect_error(response, status=409, code=40901)
    repository = face_server["app"].extensions["repository"]
    assert repository.count_group(group_id) == 1


def test_api_keys_not_leaked_in_response(client, samples):
    response = client.upload(
        "/api/v1/face/detect", files={"image": image_file(samples["face_a"])}
    )
    expect_ok(response)
    wire = response.text + str(dict(response.headers))
    assert "test-service-key" not in wire
    assert "test-iflytek-key" not in wire
    assert response.headers["X-Provider-Mode"] == "iflytek"
