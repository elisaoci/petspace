from fastapi.testclient import TestClient

from tests.helpers import API_V1


def test_health_reports_database_ok(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["ollama_model"]


def test_health_is_available_in_versioned_api(client: TestClient) -> None:
    assert client.get(f"{API_V1}/health").status_code == 200
