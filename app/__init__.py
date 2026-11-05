"""Flask application factory for the face analysis service."""

from __future__ import annotations

import logging
import re
import sys
import time
import uuid
from pathlib import Path

from flask import Flask, g, jsonify, request
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge

from .api import api
from .config import PROJECT_ROOT, Settings
from .db import Repository
from .errors import (
    ApiError,
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from .provider.base import FaceProvider
from .provider.iflytek import IFlytekClient
from .provider.mock import MockFaceProvider
from .security import IdempotencyManager
from .service import FaceService

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
VERSION = "1.0.0"


def _configure_logging(settings: Settings) -> logging.Logger:
    logger = logging.getLogger("face_service")
    logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    if logger.handlers:
        return logger
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s"
    )
    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(formatter)
    logger.addHandler(stream)
    try:
        logs = PROJECT_ROOT / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(logs / "face.log", encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError:
        pass
    logger.propagate = False
    return logger


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.request_id = g.request_id
        except (AttributeError, RuntimeError):
            record.request_id = "-"
        return True


def _build_provider(settings: Settings) -> FaceProvider:
    if settings.provider_mode == "mock":
        return MockFaceProvider()
    return IFlytekClient(
        base_url=settings.iflytek_base_url,
        app_id=settings.iflytek_app_id,
        api_key=settings.iflytek_api_key,
        timeout=settings.provider_timeout,
        retries=settings.provider_retries,
    )


def create_app(settings: Settings | None = None) -> Flask:
    settings = settings or Settings.from_env()
    repository = Repository(settings)
    provider = _build_provider(settings)
    service = FaceService(provider, repository, settings)
    idempotency = IdempotencyManager(repository, ttl_seconds=settings.idempotency_ttl)

    app = Flask(__name__)
    app.json.ensure_ascii = False
    app.json.sort_keys = False
    max_content = settings.max_image_bytes + 64 * 1024
    app.config.update(MAX_CONTENT_LENGTH=max_content, JSON_SORT_KEYS=False)
    app.extensions["settings"] = settings
    app.extensions["repository"] = repository
    app.extensions["provider"] = provider
    app.extensions["face_service"] = service
    app.extensions["idempotency"] = idempotency

    logger = _configure_logging(settings)
    for handler in logger.handlers:
        handler.addFilter(_RequestIdFilter())

    @app.before_request
    def request_context():
        incoming = request.headers.get("X-Request-ID", "")
        g.request_id = incoming if REQUEST_ID_PATTERN.fullmatch(incoming) else uuid.uuid4().hex
        g.started_at = time.perf_counter()

    @app.after_request
    def response_headers(response):
        elapsed_ms = (time.perf_counter() - getattr(g, "started_at", time.perf_counter())) * 1000
        origin = request.headers.get("Origin", "")
        if origin and origin in settings.allowed_origins:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = (
                "Content-Type, X-API-Key, Idempotency-Key, X-Request-ID"
            )
            response.headers["Access-Control-Max-Age"] = "600"
        response.headers["X-Request-ID"] = getattr(g, "request_id", "")
        response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.2f}"
        response.headers["X-Provider-Mode"] = settings.provider_mode
        logger.info(
            "%s %s -> %s %.2fms",
            request.method,
            request.path,
            response.status_code,
            elapsed_ms,
        )
        return response

    def error_payload(code: int, message: str, details=None, status: int = 400):
        body = {
            "code": code,
            "message": message,
            "data": None,
            "request_id": getattr(g, "request_id", ""),
        }
        if details is not None:
            body["details"] = details
        return jsonify(body), status

    @app.errorhandler(ApiError)
    def handle_api_error(error: ApiError):
        return error_payload(error.code, error.message, error.details, error.status)

    @app.errorhandler(ProviderAuthError)
    def handle_provider_auth(error: ProviderAuthError):
        return error_payload(50201, "上游人脸服务签名鉴权失败", {"provider": settings.provider_mode}, 502)

    @app.errorhandler(ProviderRateLimitError)
    def handle_provider_rate_limit(error: ProviderRateLimitError):
        response, status = error_payload(50301, "上游人脸服务限流，请稍后重试", None, 503)
        response.headers["Retry-After"] = "1"
        return response, status

    @app.errorhandler(ProviderTimeoutError)
    def handle_provider_timeout(error: ProviderTimeoutError):
        return error_payload(50400, "上游人脸服务超时", {"timeout": settings.provider_timeout}, 504)

    @app.errorhandler(ProviderUnavailableError)
    def handle_provider_unavailable(error: ProviderUnavailableError):
        return error_payload(50202, "上游人脸服务不可用", None, 502)

    @app.errorhandler(ProviderError)
    def handle_provider_error(error: ProviderError):
        return error_payload(50200, "上游人脸服务返回异常", None, 502)

    @app.errorhandler(RequestEntityTooLarge)
    def handle_too_large(error: RequestEntityTooLarge):
        return error_payload(41300, "上传内容超过服务限制", {"max_bytes": settings.max_image_bytes}, 413)

    @app.errorhandler(HTTPException)
    def handle_http_error(error: HTTPException):
        code_map = {404: 40400, 405: 40500, 413: 41300, 415: 41500}
        return error_payload(
            code_map.get(error.code or 500, 50000),
            error.description or "HTTP error",
            None,
            error.code or 500,
        )

    @app.errorhandler(Exception)
    def handle_unexpected(error: Exception):
        logger.exception("Unhandled exception: %s", error)
        return error_payload(50000, "服务器内部错误", None, 500)

    @app.get("/health")
    def health():
        healthy = repository.ping()
        return jsonify(
            {
                "status": "ok" if healthy else "degraded",
                "provider": settings.provider_mode,
                "database": "up" if healthy else "down",
                "version": VERSION,
            }
        ), (200 if healthy else 503)

    app.register_blueprint(api)
    logger.info(
        "Face service started env=%s provider=%s db=%s",
        settings.app_env,
        settings.provider_mode,
        settings.db_path,
    )
    return app
