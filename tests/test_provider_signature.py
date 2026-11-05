"""Signature handshake failures and app-level upstream error mapping."""

from __future__ import annotations

import base64
import time

import requests

from mock_iflytek.core import signature_headers
from tests.support import expect_error, image_file

PROVIDER_PATH = "/v1/service/v1/image_identify/face_detect"


def _provider_post(mock_provider, headers, image):
    return requests.post(
        f"{mock_provider['base_url']}{PROVIDER_PATH}",
        headers=headers,
        data={"image": base64.b64encode(image).decode("ascii")},
        timeout=10,
    )


def _valid_headers():
    return signature_headers(
        app_id="test-app",
        api_key="test-iflytek-key",
        cur_time=str(int(time.time())),
    )


def test_valid_signature_is_accepted(mock_provider, samples):
    response = _provider_post(mock_provider, _valid_headers(), samples["face_a"])
    assert response.status_code == 200
    assert response.json()["code"] == 0


def test_missing_checksum_rejected(mock_provider, samples):
    headers = _valid_headers()
    headers.pop("X-CheckSum")
    response = _provider_post(mock_provider, headers, samples["face_a"])
    assert response.status_code == 401
    assert "signature" in response.json()["message"]


def test_tampered_checksum_rejected(mock_provider, samples):
    headers = _valid_headers()
    headers["X-CheckSum"] = "0" * 32
    response = _provider_post(mock_provider, headers, samples["face_a"])
    assert response.status_code == 401


def test_expired_timestamp_rejected(mock_provider, samples):
    headers = signature_headers(
        app_id="test-app",
        api_key="test-iflytek-key",
        cur_time=str(int(time.time()) - 1000),
    )
    response = _provider_post(mock_provider, headers, samples["face_a"])
    assert response.status_code == 401
    assert "expired" in response.json()["message"]


def test_wrong_app_id_rejected(mock_provider, samples):
    headers = signature_headers(
        app_id="another-app",
        api_key="test-iflytek-key",
        cur_time=str(int(time.time())),
    )
    response = _provider_post(mock_provider, headers, samples["face_a"])
    assert response.status_code == 401


def test_app_maps_signature_failure_to_502(bad_client, samples):
    response = bad_client.upload(
        "/api/v1/face/compare",
        files={
            "image_a": image_file(samples["face_a"], "a.png"),
            "image_b": image_file(samples["face_a"], "b.png"),
        },
    )
    payload = expect_error(response, status=502, code=50201)
    assert payload["details"]["provider"] == "iflytek"
