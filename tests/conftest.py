"""Session fixtures: mock iFlytek server, face API servers and HTTP client."""

from __future__ import annotations

import threading
import uuid
from pathlib import Path
from typing import Any

import pytest
import requests
from werkzeug.serving import make_server

from app import create_app
from app.config import Settings
from mock_iflytek.app import create_app as create_mock_app
from tools.generate_samples import main as generate_samples

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_ORIGIN = "http://localhost:3000"


class FaceClient:
    def __init__(self, base_url: str, api_key: str | None = "test-service-key") -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.session = requests.Session()

    def close(self) -> None:
        self.session.close()

    def headers(self, extra: dict[str, str] | None = None, *, auth: bool = True) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if auth and self.api_key is not None:
            headers["X-API-Key"] = self.api_key
        if extra:
            headers.update(extra)
        return headers

    def request(
        self,
        method: str,
        path: str,
        *,
        auth: bool = True,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> requests.Response:
        return self.session.request(
            method,
            f"{self.base_url}{path}",
            headers=self.headers(headers, auth=auth),
            timeout=kwargs.pop("timeout", 15),
            **kwargs,
        )

    def get(self, path: str, **kwargs: Any) -> requests.Response:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> requests.Response:
        return self.request("POST", path, **kwargs)

    def upload(
        self,
        path: str,
        *,
        files: dict[str, tuple[str, bytes, str]],
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        auth: bool = True,
    ) -> requests.Response:
        return self.request(
            "POST",
            path,
            auth=auth,
            headers=headers,
            files=files,
            data=data or {},
        )


@pytest.fixture(scope="session")
def mock_provider():
    app = create_mock_app(
        app_id="test-app",
        api_key="test-iflytek-key",
        latency_ms=20,
        tolerance_seconds=300,
    )
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield {
        "base_url": f"http://127.0.0.1:{server.server_port}",
        "app": app,
        "server": server,
    }
    server.shutdown()
    thread.join(timeout=5)


def _start_app(settings: Settings):
    app = create_app(settings)
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return {
        "base_url": f"http://127.0.0.1:{server.server_port}",
        "app": app,
        "server": server,
        "thread": thread,
        "settings": settings,
    }


@pytest.fixture(scope="session")
def face_server(tmp_path_factory, mock_provider):
    db_path = tmp_path_factory.mktemp("face-api") / "face.db"
    settings = Settings(
        app_env="test",
        api_key="test-service-key",
        provider_mode="iflytek",
        iflytek_base_url=mock_provider["base_url"],
        iflytek_app_id="test-app",
        iflytek_api_key="test-iflytek-key",
        db_path=db_path,
        max_image_bytes=2 * 1024 * 1024,
        allowed_origins=(ALLOWED_ORIGIN,),
        idempotency_ttl=600,
    )
    context = _start_app(settings)
    yield context
    context["server"].shutdown()
    context["thread"].join(timeout=5)


@pytest.fixture(scope="session")
def bad_signature_server(tmp_path_factory, mock_provider):
    db_path = tmp_path_factory.mktemp("bad-face-api") / "face.db"
    settings = Settings(
        app_env="test",
        api_key="test-service-key",
        provider_mode="iflytek",
        iflytek_base_url=mock_provider["base_url"],
        iflytek_app_id="test-app",
        iflytek_api_key="wrong-iflytek-key",
        db_path=db_path,
        max_image_bytes=2 * 1024 * 1024,
        allowed_origins=(ALLOWED_ORIGIN,),
    )
    context = _start_app(settings)
    yield context
    context["server"].shutdown()
    context["thread"].join(timeout=5)


@pytest.fixture(scope="session")
def client(face_server):
    instance = FaceClient(face_server["base_url"])
    yield instance
    instance.close()


@pytest.fixture(scope="session")
def bad_client(bad_signature_server):
    instance = FaceClient(bad_signature_server["base_url"])
    yield instance
    instance.close()


@pytest.fixture(scope="session")
def samples():
    sample_dir = ROOT / "data" / "samples"
    if not (sample_dir / "face_a.png").exists():
        generate_samples()
    return {
        "face_a": (sample_dir / "face_a.png").read_bytes(),
        "face_b": (sample_dir / "face_b.png").read_bytes(),
        "face_a_jpg": (sample_dir / "face_a.jpg").read_bytes(),
        "tiny": (sample_dir / "tiny.png").read_bytes(),
        "gif": (sample_dir / "sample.gif").read_bytes(),
        "invalid": (sample_dir / "invalid.bin").read_bytes(),
        "oversized": b"\x00" * (2 * 1024 * 1024 + 1),
    }


@pytest.fixture
def group_id() -> str:
    return f"g{uuid.uuid4().hex[:10]}"


def image_file(data: bytes, filename: str = "face.png", content_type: str = "image/png"):
    return (filename, data, content_type)


@pytest.fixture
def provider_stats(mock_provider):
    def get_stats() -> dict[str, int]:
        response = requests.get(f"{mock_provider['base_url']}/stats", timeout=5)
        return response.json()["counts"]

    return get_stats
