# PetSpace backend

Таблицы создаются только миграцией (приложение не вызывает `create_all`):

```bash
alembic upgrade head
uvicorn app.main:app --reload
python -m app.seed
```

Основные endpoints находятся под `/api`: `pets` (CRUD, `/photo`, `/medical-token`,
`/public/medical-card/{token}`), `events`, `chat/stream`, `chat/history/{id}` и
`payments/demo`. Медкарта по секретному URL не возвращает `owner_notes`.
Чат передаёт поток Ollama (`OLLAMA_BASE_URL`, `OLLAMA_MODEL`) как SSE и
сохраняет историю в базе. Demo payment не принимает и не сохраняет данные карты.
