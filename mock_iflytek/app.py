"""HTTP mock of the iFlytek face WebAPI signature contract.

The public Flask app can be pointed at this server to exercise a realistic
X-Appid/X-CurTime/X-Param/X-CheckSum handshake without calling a paid API.
"""

from __future__ import annotations

import base64
import threading
import time
from typing import Any

from flask import Flask, jsonify, request

from .core import analyze, checksum, compare, detect


def create_app(
    *,
    app_id: str = "demo-app",
    api_key: str = "demo-api-key",
    latency_ms: int = 30,
    tolerance_seconds: int = 300,
) -> Flask:
    app = Flask(__name__)
    app.json.ensure_ascii = False
    state = {"detect": 0, "analyze": 0, "compare": 0, "auth_failures": 0}
    lock = threading.Lock()

    def count(name: str) -> None:
        with lock:
            state[name] += 1

    def auth_error(message: str):
        with lock:
            state["auth_failures"] += 1
        return jsonify({"code": 401, "message": message, "data": None}), 401

    def authorized():
        cur_time = request.headers.get("X-CurTime", "")
        param = request.headers.get("X-Param", "")
        supplied = request.headers.get("X-CheckSum", "")
        supplied_app = request.headers.get("X-Appid", "")
        if not cur_time or not param or not supplied or not supplied_app:
            return False, "missing signature headers"
        if supplied_app != app_id:
            return False, "invalid app id"
        try:
            if abs(time.time() - int(cur_time)) > tolerance_seconds:
                return False, "timestamp expired"
        except ValueError:
            return False, "invalid timestamp"
        expected = checksum(api_key, cur_time, param)
        if supplied != expected:
            return False, "invalid checksum"
        return True, ""

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "provider": "mock-iflytek"})

    @app.get("/stats")
    def stats():
        with lock:
            return jsonify({"status": "ok", "counts": dict(state)})

    @app.post("/v1/service/v1/image_identify/face_detect")
    def face_detect():
        ok, message = authorized()
        if not ok:
            return auth_error(message)
        count("detect")
        time.sleep(latency_ms / 1000)
        try:
            data = detect(base64.b64decode(request.form["image"]))
        except (KeyError, ValueError, base64.binascii.Error):
            return jsonify({"code": 400, "message": "invalid image payload", "data": None}), 400
        return jsonify({"code": 0, "message": "ok", "data": data})

    @app.post("/v1/service/v1/image_identify/face_analysis")
    def face_analysis():
        ok, message = authorized()
        if not ok:
            return auth_error(message)
        count("analyze")
        time.sleep(latency_ms / 1000)
        try:
            data = analyze(base64.b64decode(request.form["image"]))
        except (KeyError, ValueError, base64.binascii.Error):
            return jsonify({"code": 400, "message": "invalid image payload", "data": None}), 400
        return jsonify({"code": 0, "message": "ok", "data": data})

    @app.post("/v1/service/v1/image_identify/face_compare")
    def face_compare():
        ok, message = authorized()
        if not ok:
            return auth_error(message)
        count("compare")
        time.sleep(latency_ms / 1000)
        try:
            data = compare(
                base64.b64decode(request.form["image1"]),
                base64.b64decode(request.form["image2"]),
            )
        except (KeyError, ValueError, base64.binascii.Error):
            return jsonify({"code": 400, "message": "invalid image payload", "data": None}), 400
        return jsonify({"code": 0, "message": "ok", "data": data})

    return app
