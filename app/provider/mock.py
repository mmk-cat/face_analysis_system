"""In-process deterministic provider for zero-dependency local demos."""

from __future__ import annotations

from typing import Any

from mock_iflytek import core

from .base import FaceProvider


class MockFaceProvider(FaceProvider):
    name = "mock"

    def detect(self, image: bytes) -> dict[str, Any]:
        return core.detect(image)

    def analyze(self, image: bytes, attributes: list[str]) -> dict[str, Any]:
        return core.analyze(image, attributes)

    def compare(self, image_a: bytes, image_b: bytes) -> dict[str, Any]:
        return core.compare(image_a, image_b)
