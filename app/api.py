"""The five business HTTP endpoints (detect/analyze/compare/search/register)."""

from __future__ import annotations

from typing import Any, Callable

from flask import Blueprint, current_app, g, jsonify, request

from .security import require_api_key
from .validation import (
    fingerprint,
    parse_attributes,
    parse_group_id,
    parse_name,
    parse_person_id,
    parse_top_k,
    read_image,
)

api = Blueprint("face_api", __name__, url_prefix="/api/v1/face")


def _settings():
    return current_app.extensions["settings"]


def _service():
    return current_app.extensions["face_service"]


def _idempotency():
    return current_app.extensions["idempotency"]


def _request_id() -> str:
    return getattr(g, "request_id", "")


def _ok(data: Any, status: int = 200):
    return (
        jsonify(
            {
                "code": 0,
                "message": "ok",
                "data": data,
                "request_id": _request_id(),
            }
        ),
        status,
    )


def _idempotent(
    key: str | None,
    fp: str,
    producer: Callable[[], tuple[dict[str, Any], int]],
):
    data, status, replayed = _idempotency().execute(key, fp, producer)
    response, status_code = _ok(data, status)
    if replayed:
        response.headers["X-Idempotent-Replay"] = "true"
    return response, status_code


@api.post("/detect")
@require_api_key
def detect():
    settings = _settings()
    image = read_image("image", settings)
    key = request.headers.get("Idempotency-Key")
    fp = fingerprint("detect", [image])
    return _idempotent(key, fp, lambda: (_service().detect(image), 200))


@api.post("/analyze")
@require_api_key
def analyze():
    settings = _settings()
    image = read_image("image", settings)
    attributes = parse_attributes()
    key = request.headers.get("Idempotency-Key")
    fp = fingerprint("analyze", [image], attributes=",".join(attributes))
    return _idempotent(key, fp, lambda: (_service().analyze(image, attributes), 200))


@api.post("/compare")
@require_api_key
def compare():
    settings = _settings()
    image_a = read_image("image_a", settings)
    image_b = read_image("image_b", settings)
    key = request.headers.get("Idempotency-Key")
    fp = fingerprint("compare", [image_a, image_b])
    return _idempotent(key, fp, lambda: (_service().compare(image_a, image_b), 200))


@api.post("/search")
@require_api_key
def search():
    settings = _settings()
    image = read_image("image", settings)
    group_id = parse_group_id()
    top_k = parse_top_k(5, settings.top_k_max)
    key = request.headers.get("Idempotency-Key")
    fp = fingerprint("search", [image], group_id=group_id, top_k=top_k)
    return _idempotent(
        key, fp, lambda: (_service().search(image, group_id=group_id, top_k=top_k), 200)
    )


@api.post("/register")
@require_api_key
def register():
    settings = _settings()
    image = read_image("image", settings)
    group_id = parse_group_id()
    person_id = parse_person_id()
    name = parse_name(person_id)
    key = request.headers.get("Idempotency-Key")
    fp = fingerprint(
        "register", [image], group_id=group_id, person_id=person_id, name=name
    )
    return _idempotent(
        key,
        fp,
        lambda: (
            _service().register(
                image, group_id=group_id, person_id=person_id, name=name
            ),
            201,
        ),
    )
