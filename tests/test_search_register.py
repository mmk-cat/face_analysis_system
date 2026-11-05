"""POST /api/v1/face/register and /face/search: 1:N gallery workflow."""

from __future__ import annotations

import uuid

from tests.support import expect_error, expect_ok, image_file


def _register(
    client,
    samples,
    *,
    group_id,
    person_id="P100",
    name="Alice",
    image=None,
    key=None,
    auth=True,
    omit_person=False,
):
    data = {"group_id": group_id, "name": name}
    if not omit_person:
        data["person_id"] = person_id
    headers = {"Idempotency-Key": key} if key else None
    return client.upload(
        "/api/v1/face/register",
        files={"image": image_file(image or samples["face_a"])},
        data=data,
        headers=headers,
        auth=auth,
    )


def _search(client, samples, *, group_id, top_k=None, image=None, key=None, auth=True):
    data = {"group_id": group_id}
    if top_k is not None:
        data["top_k"] = str(top_k)
    files = {"image": image_file(image or samples["face_a"])} if image is not False else {}
    headers = {"Idempotency-Key": key} if key else None
    return client.upload(
        "/api/v1/face/search", files=files, data=data, headers=headers, auth=auth
    )


def test_register_success(client, samples, group_id):
    response = _register(client, samples, group_id=group_id, person_id="P100")
    data = expect_ok(response, 201)
    assert data["person_id"] == "P100"
    assert data["group_id"] == group_id
    assert data["name"] == "Alice"
    assert len(data["image_sha256"]) == 64
    assert data["face_count"] == 1


def test_register_duplicate_person_conflicts(client, samples, group_id):
    expect_ok(_register(client, samples, group_id=group_id, person_id="P101"), 201)
    response = _register(client, samples, group_id=group_id, person_id="P101")
    expect_error(response, status=409, code=40901)


def test_register_missing_person_id(client, samples, group_id):
    response = _register(client, samples, group_id=group_id, omit_person=True)
    expect_error(response, status=400, code=40001)


def test_register_invalid_person_id(client, samples, group_id):
    response = _register(client, samples, group_id=group_id, person_id="x")
    expect_error(response, status=400, code=40005)


def test_register_missing_image(client, samples, group_id):
    response = client.upload(
        "/api/v1/face/register",
        files={},
        data={"group_id": group_id, "person_id": "P102"},
    )
    expect_error(response, status=400, code=40001)


def test_register_oversized_image(client, samples, group_id):
    response = _register(
        client, samples, group_id=group_id, person_id="P103", image=samples["oversized"]
    )
    expect_error(response, status=413, code=41300)


def test_search_empty_group(client, samples, group_id):
    data = expect_ok(_search(client, samples, group_id=group_id))
    assert data["gallery_size"] == 0
    assert data["matches"] == []
    assert data["group_id"] == group_id


def test_search_same_face_finds_registered_person(client, samples, group_id):
    expect_ok(_register(client, samples, group_id=group_id, person_id="P200", name="Bob"), 201)
    data = expect_ok(_search(client, samples, group_id=group_id, top_k=3))
    assert data["gallery_size"] == 1
    assert data["matches"][0]["person_id"] == "P200"
    assert data["matches"][0]["same_person"] is True
    assert data["matches"][0]["similarity"] >= 0.9


def test_search_different_face_is_not_same_person(client, samples, group_id):
    expect_ok(_register(client, samples, group_id=group_id, person_id="P201"), 201)
    data = expect_ok(_search(client, samples, group_id=group_id, image=samples["face_b"]))
    assert data["matches"]
    assert data["matches"][0]["same_person"] is False
    assert data["matches"][0]["similarity"] < 0.75


def test_search_missing_image(client, samples, group_id):
    response = _search(client, samples, group_id=group_id, image=False)
    expect_error(response, status=400, code=40001)


def test_search_top_k_zero(client, samples, group_id):
    response = _search(client, samples, group_id=group_id, top_k=0)
    expect_error(response, status=400, code=40005)


def test_search_top_k_too_large(client, samples, group_id):
    response = _search(client, samples, group_id=group_id, top_k=51)
    expect_error(response, status=400, code=40005)


def test_search_top_k_must_be_integer(client, samples, group_id):
    response = client.upload(
        "/api/v1/face/search",
        files={"image": image_file(samples["face_a"])},
        data={"group_id": group_id, "top_k": "true"},
    )
    expect_error(response, status=400, code=40005)


def test_search_top_k_rejects_non_ascii_digits(client, samples, group_id):
    response = client.upload(
        "/api/v1/face/search",
        files={"image": image_file(samples["face_a"])},
        data={"group_id": group_id, "top_k": "１"},
    )
    expect_error(response, status=400, code=40005)


def test_search_invalid_group_id(client, samples):
    response = _search(client, samples, group_id="bad group")
    expect_error(response, status=400, code=40005)


def test_search_requires_api_key(client, samples, group_id):
    response = _search(client, samples, group_id=group_id, auth=False)
    expect_error(response, status=401, code=40100)


def test_search_duplicate_key(client, samples, group_id, provider_stats):
    expect_ok(_register(client, samples, group_id=group_id, person_id="P202"), 201)
    key = f"search-{uuid.uuid4().hex}"
    before = provider_stats()
    first = _search(client, samples, group_id=group_id, key=key)
    second = _search(client, samples, group_id=group_id, key=key)
    data1 = expect_ok(first)
    data2 = expect_ok(second)
    assert data1["matches"] == data2["matches"]
    assert second.headers["X-Idempotent-Replay"] == "true"
    assert provider_stats()["compare"] - before["compare"] == 1
