"""Standalone mock iFlytek server for local demos and JMeter."""

from __future__ import annotations

import argparse

from .app import create_app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5100)
    parser.add_argument("--latency-ms", type=int, default=30)
    parser.add_argument("--app-id", default="demo-app")
    parser.add_argument("--api-key", default="demo-api-key")
    args = parser.parse_args()
    app = create_app(
        app_id=args.app_id,
        api_key=args.api_key,
        latency_ms=args.latency_ms,
    )
    app.run(host="127.0.0.1", port=args.port, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()
