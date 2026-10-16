from fastapi.testclient import TestClient

from app.config import get_settings


def test_history_is_empty_for_new_conversation(client: TestClient) -> None:
    response = client.get("/api/chat/history/nothing-here")

    assert response.status_code == 200
    assert response.json() == []


def test_history_can_be_cleared(client: TestClient, pet: dict) -> None:
    client.post(
        "/api/chat/stream",
        json={"message": "Привет", "conversation_id": "to-clear", "pet_id": pet["id"]},
    )
    assert client.get("/api/chat/history/to-clear").json()

    assert client.delete("/api/chat/history/to-clear").status_code == 204
    assert client.get("/api/chat/history/to-clear").json() == []


def test_stream_reports_error_when_ollama_unavailable(client: TestClient, pet: dict, monkeypatch) -> None:
    # Порт 9 закрыт: имитируем недоступную модель.
    monkeypatch.setattr(get_settings(), "ollama_base_url", "http://127.0.0.1:9")

    response = client.post(
        "/api/chat/stream",
        json={"message": "Сколько корма давать?", "conversation_id": "offline", "pet_id": pet["id"]},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert '"error"' in response.text
    assert response.text.rstrip().endswith("data: [DONE]")

    # Сообщение владельца сохраняется даже при сбое модели.
    history = client.get("/api/chat/history/offline").json()
    assert [message["role"] for message in history] == ["user"]


def test_stream_validates_empty_message(client: TestClient) -> None:
    response = client.post("/api/chat/stream", json={"message": ""})

    assert response.status_code == 422
