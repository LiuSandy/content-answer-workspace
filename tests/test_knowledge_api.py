from fastapi.testclient import TestClient
import pytest
from app.bootstrap.server import app

client = TestClient(app)


def test_knowledge_api_endpoints():
    response = client.get("/api/knowledge/documents?workspaceId=default")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "documents" in data["data"]
