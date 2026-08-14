from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.infrastructure.observability.middleware import RequestLoggingMiddleware


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)

    @app.get("/health")
    async def health():
        return {"ok": True}

    return app


def test_request_id_is_generated_and_returned():
    with TestClient(_app()) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.headers["x-request-id"].startswith("req_")


def test_valid_request_id_is_preserved_and_invalid_replaced():
    with TestClient(_app()) as client:
        preserved = client.get("/health", headers={"X-Request-ID": "client-123"})
        replaced = client.get("/health", headers={"X-Request-ID": "bad id with spaces"})
    assert preserved.headers["x-request-id"] == "client-123"
    assert replaced.headers["x-request-id"] != "bad id with spaces"
