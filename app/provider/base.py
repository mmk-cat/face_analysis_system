"""Provider abstraction: in-process mock or real iFlytek WebAPI."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class FaceProvider(ABC):
    name = "base"

    @abstractmethod
    def detect(self, image: bytes) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def analyze(self, image: bytes, attributes: list[str]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def compare(self, image_a: bytes, image_b: bytes) -> dict[str, Any]:
        raise NotImplementedError
