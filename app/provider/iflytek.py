"""iFlytek face WebAPI client with MD5 checksum signing and strict errors."""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..errors import (
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from .base import FaceProvider

DETECT_PATH = "/v1/service/v1/image_identify/face_detect"
ANALYZE_PATH = "/v1/service/v1/image_identify/face_analysis"
COMPARE_PATH = "/v1/service/v1/image_identify/face_compare"


class IFlytekClient(FaceProvider):
    name = "iflytek"

    def __init__(
        self,
        *,
        base_url: str,
        app_id: str,
        api_key: str,
        timeout: float = 3.0,
        retries: int = 1,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.app_id = app_id
        self.api_key = api_key
        self.timeout = timeout
        retry = Retry(
            total=retries,
            connect=retries,
            read=0,
            status=retries,
            status_forcelist=(429, 502, 503, 504),
            allowed_methods=frozenset({"POST"}),
            backoff_factor=0.1,
            respect_retry_after_header=True,
            raise_on_status=False,
        )
        self.session = requests.Session()
        self.session.mount("http://", HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=30))
        self.session.mount("https://", HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=30))

    def _headers(self) -> dict[str, str]:
        import time

        cur_time = str(int(time.time()))
        param = base64.b64encode(
            json.dumps({"service": "face"}, separators=(",", ":")).encode("utf-8")
        ).decode("ascii")
        checksum = hashlib.md5(
            f"{self.api_key}{cur_time}{param}".encode("utf-8")
        ).hexdigest()
        return {
            "X-Appid": self.app_id,
            "X-CurTime": cur_time,
            "X-Param": param,
            "X-CheckSum": checksum,
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
            "Accept": "application/json",
        }

    def _call(self, path: str, form: dict[str, str]) -> dict[str, Any]:
        try:
            response = self.session.post(
                f"{self.base_url}{path}",
                headers=self._headers(),
                data=form,
                timeout=self.timeout,
            )
        except requests.Timeout as exc:
            raise ProviderTimeoutError("iFlytek request timed out") from exc
        except requests.RequestException as exc:
            raise ProviderUnavailableError(f"iFlytek request failed: {exc}") from exc
        if response.status_code in {401, 403}:
            raise ProviderAuthError(f"iFlytek signature rejected: {response.text[:200]}")
        if response.status_code == 429:
            raise ProviderRateLimitError("iFlytek rate limited")
        if response.status_code >= 500:
            raise ProviderUnavailableError(f"iFlytek HTTP {response.status_code}")
        if response.status_code != 200:
            raise ProviderError(f"iFlytek HTTP {response.status_code}: {response.text[:200]}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderError("iFlytek returned non-JSON") from exc
        if payload.get("code") != 0:
            raise ProviderError(f"iFlytek business error: {payload}")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise ProviderError("iFlytek response missing data object")
        return data

    def detect(self, image: bytes) -> dict[str, Any]:
        return self._call(DETECT_PATH, {"image": base64.b64encode(image).decode("ascii")})

    def analyze(self, image: bytes, attributes: list[str]) -> dict[str, Any]:
        return self._call(
            ANALYZE_PATH,
            {
                "image": base64.b64encode(image).decode("ascii"),
                "attributes": json.dumps(attributes, ensure_ascii=False),
            },
        )

    def compare(self, image_a: bytes, image_b: bytes) -> dict[str, Any]:
        return self._call(
            COMPARE_PATH,
            {
                "image1": base64.b64encode(image_a).decode("ascii"),
                "image2": base64.b64encode(image_b).decode("ascii"),
            },
        )
