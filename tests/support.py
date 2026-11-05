"""Tiny HTTP assertion helpers for the face API tests."""

from __future__ import annotations

import pytest
import requests


def image_file(data: bytes, filename: str = "face.png", content_type: str = "image/png"):
    return (filename, data, content_type)


def body(response: requests.Response) -> dict:
    try:
        payload = response.json()
    except ValueError:
        pytest.fail(f"Expected JSON, got {response.status_code}: {response.text[:1000]}")
    assert isinstance(payload, dict)
    return payload


def expect_ok(response: requests.Response, status: int = 200) -> dict:
    assert response.status_code == status, response.text
    payload = body(response)
    assert payload.get("code") == 0, payload
    assert payload.get("request_id"), payload
    return payload["data"]


def expect_error(response: requests.Response, *, status: int, code: int) -> dict:
    assert response.status_code == status, response.text
    payload = body(response)
    assert payload.get("code") == code, payload
    assert payload.get("request_id"), payload
    return payload
