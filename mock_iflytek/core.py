"""Deterministic face provider core shared by the in-process mock and the mock HTTP server.

This is explicitly a mock: it validates images and returns stable synthetic
attributes/similarity.  It is not a real face-recognition model.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
from typing import Any

from PIL import Image, UnidentifiedImageError

EMOTIONS = ["neutral", "happy", "surprised", "calm"]


def _load(image_bytes: bytes) -> tuple[int, int, str]:
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            image.verify()
        with Image.open(io.BytesIO(image_bytes)) as image:
            return image.width, image.height, hashlib.sha256(image_bytes).hexdigest()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValueError("invalid image") from exc


def detect(image_bytes: bytes) -> dict[str, Any]:
    width, height, digest = _load(image_bytes)
    box = {
        "x": int(width * 0.18),
        "y": int(height * 0.14),
        "width": int(width * 0.64),
        "height": int(height * 0.72),
    }
    return {
        "face_count": 1,
        "width": width,
        "height": height,
        "faces": [
            {
                "bbox": box,
                "confidence": 0.992,
                "quality": round(0.86 + int(digest[:2], 16) % 12 / 100, 3),
            }
        ],
    }


def analyze(image_bytes: bytes, attributes: list[str] | None = None) -> dict[str, Any]:
    width, height, digest = _load(image_bytes)
    age = 20 + int(digest[:2], 16) % 26
    face = {
        "age": age,
        "gender": "female" if int(digest[2:4], 16) % 2 == 0 else "male",
        "glasses": int(digest[4:6], 16) % 3 == 0,
        "mask": int(digest[6:8], 16) % 4 == 0,
        "emotion": EMOTIONS[int(digest[8:10], 16) % len(EMOTIONS)],
        "quality": round(0.85 + int(digest[10:12], 16) % 14 / 100, 3),
        "bbox": {
            "x": int(width * 0.18),
            "y": int(height * 0.14),
            "width": int(width * 0.64),
            "height": int(height * 0.72),
        },
    }
    selected = attributes or list(face.keys())
    return {"face": {key: face[key] for key in selected if key in face}}


def compare(image_a: bytes, image_b: bytes) -> dict[str, Any]:
    _, _, digest_a = _load(image_a)
    _, _, digest_b = _load(image_b)
    if digest_a == digest_b:
        similarity = 0.982
    else:
        similarity = round(0.10 + (int(digest_a[:4], 16) ^ int(digest_b[:4], 16)) % 8 / 100, 3)
    return {
        "similarity": similarity,
        "same_person": similarity >= 0.75,
        "threshold": 0.75,
    }


def param_b64() -> str:
    raw = json.dumps({"service": "face"}, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


def checksum(api_key: str, cur_time: str, param: str) -> str:
    return hashlib.md5(f"{api_key}{cur_time}{param}".encode("utf-8")).hexdigest()


def signature_headers(
    *, app_id: str, api_key: str, cur_time: str | None = None
) -> dict[str, str]:
    import time

    current = cur_time or str(int(time.time()))
    param = param_b64()
    return {
        "X-Appid": app_id,
        "X-CurTime": current,
        "X-Param": param,
        "X-CheckSum": checksum(api_key, current, param),
        "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
    }
