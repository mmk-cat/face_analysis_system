"""Health, CORS, routing and request tracing contract."""

from __future__ import annotations

import re

import pytest

from tests.support import expect_error, expect_ok


def test_health_is_public(client):
    response = client.get("/health", auth=False)
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["provider"] == "iflytek"
    assert payload["database"] == "up"
    assert response.headers["X-Request-ID"]


def test_health_cors_allowed(client):
    response = client.get("/health", auth=False, headers={"Origin": "http://localhost:3000"})
    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"
    assert "Origin" in response.headers.get("Vary", "")


def test_cors_disallowed_origin_has_no_header(client):
    response = client.get("/health", auth=False, headers={"Origin": "https://evil.example.com"})
    assert response.status_code == 200
    assert "Access-Control-Allow-Origin" not in response.headers


def test_unknown_route_is_json(client):
    response = client.get("/api/v1/face/no-such-route")
    payload = expect_error(response, status=404, code=40400)
    assert payload["request_id"]


def test_method_not_allowed_is_json(client):
    response = client.request("DELETE", "/health")
    expect_error(response, status=405, code=40500)


def test_custom_request_id_echoed(client):
    request_id = "face-contract-2026"
    response = client.get("/health", auth=False, headers={"X-Request-ID": request_id})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == request_id


def test_invalid_request_id_replaced(client):
    response = client.get("/health", auth=False, headers={"X-Request-ID": "bad id with spaces"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] != "bad id with spaces"
    assert re.fullmatch(r"[0-9a-f]{32}", response.headers["X-Request-ID"])
