"""Multipart/image/form validation with clear business error codes."""

from __future__ import annotations

import io
import json
import re
from dataclasses import dataclass
from typing import Any

from flask import request
from PIL import Image, UnidentifiedImageError

from .config import Settings
from .errors import ApiError

Image.MAX_IMAGE_PIXELS = 30_000_000
SUPPORTED_FORMATS = {"PNG", "JPEG", "WEBP"}
ALLOWED_ATTRIBUTES = {"age", "gender", "glasses", "mask", "emotion", "quality"}
GROUP_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
PERSON_PATTERN = re.compile(r"^[A-Za-z0-9_-]{3,32}$")


@dataclass
class UploadedImage:
    data: bytes
    filename: str
    mimetype: str
    width: int
    height: int
    image_format: str


def _decode_image(data: bytes, settings: Settings, field: str) -> tuple[int, int, str]:
    try:
        with Image.open(io.BytesIO(data)) as probe:
            image_format = (probe.format or "").upper()
            width, height = probe.size
            probe.verify()
        if image_format not in SUPPORTED_FORMATS:
            raise ApiError(415, 41500, f"{field} 仅支持 PNG/JPEG/WEBP", {"format": image_format})
        if width < settings.min_image_side or height < settings.min_image_side:
            raise ApiError(
                422,
                42202,
                f"{field} 分辨率至少 {settings.min_image_side}×{settings.min_image_side}",
                {"width": width, "height": height},
            )
        if width > settings.max_image_side or height > settings.max_image_side:
            raise ApiError(422, 42203, f"{field} 分辨率超过限制", {"width": width, "height": height})
        return width, height, image_format
    except Image.DecompressionBombError as exc:
        raise ApiError(422, 42204, f"{field} 图片像素过大") from exc
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ApiError(400, 40003, f"{field} 不是有效图片") from exc


def read_image(field: str, settings: Settings, *, required: bool = True) -> UploadedImage | None:
    if field not in request.files:
        if not required:
            return None
        raise ApiError(400, 40001, f"缺少文件字段 {field}", {"field": field})
    storage = request.files[field]
    filename = storage.filename or ""
    if not filename:
        raise ApiError(400, 40002, f"{field} 文件名为空", {"field": field})
    data = storage.read(settings.max_image_bytes + 1)
    if not data:
        raise ApiError(400, 40002, f"{field} 文件为空", {"field": field})
    if len(data) > settings.max_image_bytes:
        raise ApiError(
            413,
            41300,
            f"{field} 超过 {settings.max_image_bytes} 字节限制",
            {"max_bytes": settings.max_image_bytes, "actual_bytes": len(data)},
        )
    width, height, image_format = _decode_image(data, settings, field)
    return UploadedImage(
        data=data,
        filename=filename,
        mimetype=storage.mimetype or "",
        width=width,
        height=height,
        image_format=image_format,
    )


def parse_attributes(default: list[str] | None = None) -> list[str]:
    raw = request.form.get("attributes")
    if raw is None or raw == "":
        return list(default or ["age", "gender", "glasses", "mask"])
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ApiError(400, 40005, "attributes 必须是合法 JSON 数组") from exc
    if not isinstance(parsed, list) or not parsed:
        raise ApiError(400, 40005, "attributes 必须是非空数组")
    if any(not isinstance(item, str) for item in parsed):
        raise ApiError(400, 40005, "attributes 数组元素必须是字符串")
    unknown = [item for item in parsed if item not in ALLOWED_ATTRIBUTES]
    if unknown:
        raise ApiError(400, 40005, f"不支持的属性: {', '.join(unknown)}")
    # Preserve request order while removing duplicates.
    return list(dict.fromkeys(parsed))


def parse_top_k(default: int, maximum: int) -> int:
    raw = request.form.get("top_k", str(default))
    if not re.fullmatch(r"[0-9]+", raw):
        raise ApiError(400, 40005, "top_k 必须是整数")
    value = int(raw)
    if value < 1 or value > maximum:
        raise ApiError(400, 40005, f"top_k 必须在 1 到 {maximum} 之间")
    return value


def parse_group_id(default: str = "default") -> str:
    raw = request.form.get("group_id", default)
    if not GROUP_PATTERN.fullmatch(raw):
        raise ApiError(400, 40005, "group_id 只能包含字母、数字、下划线、连字符")
    return raw


def parse_person_id() -> str:
    raw = request.form.get("person_id", "")
    if not raw:
        raise ApiError(400, 40001, "缺少 person_id", {"field": "person_id"})
    if not PERSON_PATTERN.fullmatch(raw):
        raise ApiError(400, 40005, "person_id 需为 3-32 位字母/数字/下划线/连字符")
    return raw


def parse_name(person_id: str) -> str:
    raw = request.form.get("name", person_id).strip()
    if not raw:
        return person_id
    if len(raw) > 50:
        raise ApiError(400, 40005, "name 长度不能超过 50")
    return raw


def fingerprint(endpoint: str, images: list[UploadedImage], **form_values: Any) -> str:
    import hashlib

    digest = hashlib.sha256()
    digest.update(endpoint.encode("utf-8"))
    for image in images:
        digest.update(b"\x00")
        digest.update(image.data)
    for key in sorted(form_values):
        digest.update(f"|{key}={form_values[key]}".encode("utf-8"))
    return digest.hexdigest()
