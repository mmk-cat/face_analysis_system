"""Deliberately unoptimized compare endpoint used as the benchmark baseline.

It performs three serial upstream calls (detect A, detect B, compare) and opens
a new HTTP connection for every call.  The optimized API performs one
face_compare call through a pooled session.  This is a benchmark fixture, not a
production endpoint.
"""

from __future__ import annotations

import base64
import os
import time
from typing import Any

import requests
from flask import Flask, jsonify, request

from mock_iflytek.core import signature_headers


def create_app(provider_base: str, *, app_id: str, api_key: str) -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024

    def call(path: str, form: dict[str, str]) -> dict[str, Any]:
        response = requests.post(
            f"{provider_base}{path}",
            headers=signature_headers(app_id=app_id, api_key=api_key),
            data=form,
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 0:
            raise RuntimeError(payload)
        return payload["data"]

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.post("/api/v1/face/compare")
    def compare():
        started = time.perf_counter()
        try:
            a = request.files["image_a"].read()
            b = request.files["image_b"].read()
            call(
                "/v1/service/v1/image_identify/face_detect",
                {"image": base64.b64encode(a).decode("ascii")},
            )
            call(
                "/v1/service/v1/image_identify/face_detect",
                {"image": base64.b64encode(b).decode("ascii")},
            )
            result = call(
                "/v1/service/v1/image_identify/face_compare",
                {
                    "image1": base64.b64encode(a).decode("ascii"),
                    "image2": base64.b64encode(b).decode("ascii"),
                },
            )
        except Exception as exc:  # baseline keeps the failure visible
            return jsonify({"error": str(exc)}), 502
        return jsonify(
            {
                "code": 0,
                "similarity": result["similarity"],
                "same_person": result["same_person"],
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
            }
        )

    return app


if __name__ == "__main__":
    from werkzeug.serving import run_simple

    run_simple(
        "127.0.0.1",
        int(os.getenv("PORT", "5004")),
        create_app(
            os.getenv("PROVIDER_URL", "http://127.0.0.1:5100"),
            app_id="demo-app",
            api_key="demo-api-key",
        ),
        threaded=True,
    )
