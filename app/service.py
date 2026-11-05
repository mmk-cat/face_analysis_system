"""Business orchestration for detect/analyze/compare/search/register."""

from __future__ import annotations

import hashlib
import time
from typing import Any

from .config import Settings
from .db import DuplicatePersonError, Repository
from .errors import ApiError
from .provider.base import FaceProvider
from .validation import UploadedImage


class FaceService:
    def __init__(self, provider: FaceProvider, repository: Repository, settings: Settings) -> None:
        self.provider = provider
        self.repository = repository
        self.settings = settings

    def _timing(self, started: float) -> dict[str, Any]:
        return {
            "provider": self.settings.provider_mode,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        }

    def detect(self, image: UploadedImage) -> dict[str, Any]:
        started = time.perf_counter()
        result = self.provider.detect(image.data)
        if int(result.get("face_count", 0)) <= 0:
            raise ApiError(422, 42200, "未检测到人脸")
        return {**result, **self._timing(started)}

    def analyze(self, image: UploadedImage, attributes: list[str]) -> dict[str, Any]:
        started = time.perf_counter()
        result = self.provider.detect(image.data)
        if int(result.get("face_count", 0)) <= 0:
            raise ApiError(422, 42200, "未检测到人脸")
        analysis = self.provider.analyze(image.data, attributes)
        face = analysis.get("face", {})
        face = {key: value for key, value in face.items() if key in attributes}
        return {
            "face": face,
            "attributes": attributes,
            **self._timing(started),
        }

    def compare(self, image_a: UploadedImage, image_b: UploadedImage) -> dict[str, Any]:
        started = time.perf_counter()
        result = self.provider.compare(image_a.data, image_b.data)
        similarity = float(result.get("similarity", 0))
        threshold = float(result.get("threshold", self.settings.face_threshold))
        return {
            "similarity": round(similarity, 4),
            "threshold": threshold,
            "same_person": bool(result.get("same_person", similarity >= threshold)),
            **self._timing(started),
        }

    def register(
        self,
        image: UploadedImage,
        *,
        group_id: str,
        person_id: str,
        name: str,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        detection = self.provider.detect(image.data)
        if int(detection.get("face_count", 0)) <= 0:
            raise ApiError(422, 42200, "未检测到人脸，无法注册")
        digest = hashlib.sha256(image.data).hexdigest()
        try:
            person = self.repository.add_person(
                group_id=group_id,
                person_id=person_id,
                name=name,
                image_sha256=digest,
                image_bytes=image.data,
            )
        except DuplicatePersonError as exc:
            raise ApiError(409, 40901, "该分组下 person_id 已存在") from exc
        return {
            **person,
            "face_count": int(detection.get("face_count", 0)),
            **self._timing(started),
        }

    def search(self, image: UploadedImage, *, group_id: str, top_k: int) -> dict[str, Any]:
        started = time.perf_counter()
        gallery = self.repository.list_group(group_id, limit=self.settings.max_gallery)
        matches: list[dict[str, Any]] = []
        for person in gallery:
            result = self.provider.compare(image.data, person["image_bytes"])
            similarity = round(float(result.get("similarity", 0)), 4)
            threshold = float(result.get("threshold", self.settings.face_threshold))
            matches.append(
                {
                    "person_id": person["person_id"],
                    "name": person["name"],
                    "similarity": similarity,
                    "same_person": bool(result.get("same_person", similarity >= threshold)),
                }
            )
        matches.sort(key=lambda item: (-item["similarity"], item["person_id"]))
        return {
            "group_id": group_id,
            "gallery_size": len(gallery),
            "top_k": top_k,
            "matches": matches[:top_k],
            **self._timing(started),
        }
