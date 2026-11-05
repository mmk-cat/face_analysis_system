"""API-key auth and in-process idempotency coordination."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import threading
import time
from contextlib import contextmanager
from typing import Any, Callable, Iterator

from flask import current_app, request

from .errors import ApiError
from .db import Repository

KEY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def require_api_key(func: Callable) -> Callable:
    def wrapper(*args: Any, **kwargs: Any):
        supplied = request.headers.get("X-API-Key", "")
        expected = current_app.extensions["settings"].api_key
        if not supplied:
            raise ApiError(401, 40100, "缺少 X-API-Key")
        if not hmac.compare_digest(supplied, expected):
            raise ApiError(401, 40101, "X-API-Key 无效")
        return func(*args, **kwargs)

    wrapper.__name__ = func.__name__
    wrapper.__doc__ = func.__doc__
    return wrapper


def sha256_hex(*parts: bytes) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part)
    return digest.hexdigest()


class IdempotencyManager:
    """Serialize same-key requests and replay the first successful data payload.

    This is a single-process implementation backed by SQLite.  For a multi-replica
    deployment the same rows can be placed behind Redis/MySQL with a unique-key
    insert; the HTTP contract stays unchanged.
    """

    def __init__(self, repository: Repository, ttl_seconds: int = 600) -> None:
        self.repository = repository
        self.ttl_seconds = ttl_seconds
        self._locks: dict[str, tuple[threading.Lock, int]] = {}
        self._locks_guard = threading.Lock()

    @contextmanager
    def _lock_for(self, key: str) -> Iterator[None]:
        with self._locks_guard:
            lock, waiters = self._locks.get(key, (threading.Lock(), 0))
            self._locks[key] = (lock, waiters + 1)
        try:
            with lock:
                yield
        finally:
            with self._locks_guard:
                lock, waiters = self._locks[key]
                if waiters <= 1:
                    self._locks.pop(key, None)
                else:
                    self._locks[key] = (lock, waiters - 1)

    def execute(
        self,
        key: str | None,
        fingerprint: str,
        producer: Callable[[], tuple[dict[str, Any], int]],
    ) -> tuple[dict[str, Any], int, bool]:
        if key is None:
            data, status = producer()
            return data, status, False
        if not KEY_PATTERN.fullmatch(key):
            raise ApiError(400, 40006, "Idempotency-Key 格式非法")
        now = time.time()
        self.repository.delete_expired_idempotency(now - self.ttl_seconds)
        with self._lock_for(key):
            cached = self.repository.get_idempotency(key)
            if cached and now - float(cached["created_at"]) <= self.ttl_seconds:
                if cached["fingerprint"] != fingerprint:
                    raise ApiError(409, 40900, "相同 Idempotency-Key 的请求参数不一致")
                return json.loads(cached["data_json"]), int(cached["status"]), True
            data, status = producer()
            if 200 <= status < 300:
                self.repository.save_idempotency(
                    key=key,
                    fingerprint=fingerprint,
                    status=status,
                    data_json=json.dumps(data, ensure_ascii=False),
                    created_at=now,
                )
            return data, status, False
