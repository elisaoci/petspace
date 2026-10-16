# PetSpace

Сайт для профиля питомца, календаря здоровья, локального ИИ-помощника и демо-подписки PetSpace Plus.

- Frontend: React 18 + TypeScript, Vite 5, React Router 6, Tailwind CSS — порт **5173**
- Backend: FastAPI + SQLAlchemy 2.0 + Alembic — порт **8000**, Swagger на `/docs`
- БД: PostgreSQL 16 — внутри compose `db:5432`, на хост публикуется как **5433** (`POSTGRES_PORT`)
- ИИ: Ollama на хосте (по умолчанию модель `qwen2.5:3b`), ответы стримятся по SSE

Страницы: `/` главная, `/app` кабинет, `/app/pet`, `/app/calendar`, `/app/chat`, `/plus`, `/medical/:token`.

## Быстрый старт (Docker Compose)

```bash
cp .env.example .env
docker compose -p petspace up -d --build
docker compose -p petspace exec backend python -m app.seed
```

Откройте http://localhost:5173 (Swagger — http://localhost:8000/docs).

Флаг `-d` обязателен, если вы не хотите держать терминал занятым: без него `Ctrl+C` останавливает контейнеры.

Миграции Alembic применяются автоматически: в `docker-compose.yml` backend запускается командой
`alembic upgrade head && uvicorn app.main:app ...` и ждёт healthcheck базы. Сидер (`app.seed`) создаёт
питомца «Макс» с двумя событиями календаря — без него кабинет будет пустым.

Проверка, что всё живо:

```bash
docker compose -p petspace ps
curl http://localhost:8000/api/health   # {"status":"ok","database":"ok","ollama_model":"qwen2.5:3b"}
curl http://localhost:5173/ -o /dev/null -w "%{http_code}\n"   # 200
```

Полезные команды:

```bash
docker compose -p petspace logs -f frontend     # логи
docker compose -p petspace restart backend      # перезапуск
docker compose -p petspace down                 # остановить (данные БД сохраняются в volume)
docker compose -p petspace down -v              # остановить и удалить БД
docker compose -p petspace exec backend alembic upgrade head   # вручную применить миграции
```

Данные живут в именованных volumes: `postgres_data` (база) и `uploads_data` (фото питомцев и вложения,
монтируется в `/app/uploads`). Обычный `down` их сохраняет, удаляет только `down -v`.

## ИИ-помощник: Ollama на хосте

Ollama работает **на хосте, а не в контейнере** — модель крутится на вашем железе.

```bash
brew install ollama        # macOS; альтернатива — установщик с https://ollama.com/download
ollama pull qwen2.5:3b     # ~2 ГБ, скачивается один раз
curl http://localhost:11434/api/tags   # проверка, что сервер отвечает
```

Сам сервер запускается одним из двух способов:

```bash
brew services start ollama   # рекомендуется: работает в фоне и поднимается при входе в систему
ollama serve                 # либо вручную, в отдельном терминале (умрёт вместе с терминалом)
```

Остановить фоновый сервис — `brew services stop ollama`, посмотреть состояние — `brew services list`.

Адрес Ollama для backend задаётся переменной `OLLAMA_BASE_URL`:

- Docker (по умолчанию в `docker-compose.yml`): `http://host.docker.internal:11434`
- локальный backend без Docker: `http://localhost:11434`

Модель переключается переменной `OLLAMA_MODEL`. Если Ollama не запущена, страницы работают,
но в чате появится ошибка в SSE-потоке — это ожидаемое поведение.

Проверить чат без браузера (первый ответ после простоя ждёт загрузки модели 5–30 с):

```bash
curl -N -X POST http://localhost:8000/api/chat/stream \
  -H 'Content-Type: application/json' \
  -d '{"message":"Сколько корма давать ретриверу 32 кг?","conversation_id":"smoke","pet_id":1}'
```

В ответ придёт поток `data: {"content": "..."}` и завершающий `data: [DONE]`. Тестовую переписку
можно удалить: `curl -X DELETE http://localhost:8000/api/chat/history/smoke`.

## Локальный запуск без Docker

Backend (нужна доступная PostgreSQL):

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=postgresql+psycopg://petspace:petspace@localhost:5433/petspace
export OLLAMA_BASE_URL=http://localhost:11434
alembic upgrade head
python -m app.seed
uvicorn app.main:app --reload
```

Postgres проще всего поднять из того же compose: `docker compose -p petspace up -d db`.
Порт `5433` — опубликованный порт контейнера (см. `POSTGRES_PORT` ниже); если 5432 у вас свободен,
верните `5432`.

Backend читает `.env` из **своей рабочей папки** (`env_file=".env"` в `app/config.py`), поэтому при
запуске из `backend/` нужен `backend/.env`, либо переменные окружения, как выше.

Frontend:

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173
```

`VITE_API_URL` по умолчанию `http://localhost:8000/api` (см. `src/lib/api.ts`) — для локального
запуска менять ничего не нужно.

## Тесты и линтер

Backend проверяется на настоящем PostgreSQL, но в отдельной базе `petspace_test`:

```bash
docker compose -p petspace up -d db
docker compose -p petspace exec -T db psql -U petspace -d postgres -c 'CREATE DATABASE petspace_test'
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
export TEST_DATABASE_URL=postgresql+psycopg://petspace:petspace@localhost:5433/petspace_test
ruff check .
pytest
```

Тесты покрывают CRUD питомцев, загрузку фото, вычисление `overdue`, публичную медкарту (в том числе
что заметки владельца в неё не попадают и что перевыпуск токена ломает старую ссылку) и деградацию
чата при недоступной модели. Frontend проверяется типами при сборке — `npm run build`.

## CI

`.github/workflows/ci.yml` запускается на каждый push в `main` и на pull request:

- **backend** — `ruff check` и `pytest` с сервисным PostgreSQL;
- **frontend** — `npm ci` и `npm run build`;
- **docker** — сборка обоих образов, запуск frontend-контейнера и проверка, что `/`, `/app` и `/plus`
  отвечают 200. Это регрессия на два уже исправленных бага: `vite: Permission denied`
  (node_modules с macOS в образе) и конфликт `WORKDIR /app` с маршрутом SPA `/app`.

## Переменные окружения

| Переменная | Назначение | Значение по умолчанию |
| --- | --- | --- |
| `DATABASE_URL` | строка подключения SQLAlchemy | `postgresql+psycopg://petspace:petspace@localhost:5432/petspace` |
| `POSTGRES_PORT` | порт Postgres **на хосте** (внутри compose всегда `db:5432`) | `5432`, в `.env.example` — `5433` |
| `OLLAMA_BASE_URL` | адрес Ollama | `http://localhost:11434` |
| `OLLAMA_MODEL` | модель для чата | `qwen2.5:3b` |
| `VITE_API_URL` | база API для фронтенда | `http://localhost:8000/api` |
| `UPLOAD_DIR` | папка загруженных фото | `uploads` |

Почему на хосте `5433`: на 5432 часто уже слушает локальный Postgres/Postgres.app, и тогда
подключение с хоста перехватывает он — появляется `FATAL: role "petspace" does not exist`, хотя в
контейнере всё в порядке. Порт меняется одной строкой в `.env`, сеть контейнеров не затрагивается:
backend всегда ходит на `db:5432`.

## API

| Метод | Путь | Что делает |
| --- | --- | --- |
| GET | `/api/health` | статус сервиса, БД и имя модели |
| GET/POST | `/api/pets` | список и создание питомцев |
| GET/PATCH/DELETE | `/api/pets/{id}` | карточка питомца |
| POST | `/api/pets/{id}/photo` | загрузка фото (jpg, jpeg, png, webp) |
| POST | `/api/pets/{id}/medical-token` | перевыпуск секретной ссылки медкарты |
| GET | `/api/pets/public/medical-card/{token}` | публичная медкарта без заметок владельца |
| GET/POST | `/api/events` | календарь (фильтр `?pet_id=`), у каждого события есть `computed_status` |
| GET/PATCH/DELETE | `/api/events/{id}` | редактирование события |
| POST | `/api/chat/stream` | SSE-поток ответа Ollama с контекстом питомца |
| GET/DELETE | `/api/chat/history/{conversation_id}` | история и очистка диалога |
| POST | `/api/payments/demo` | заглушка демо-оплаты: карта не обрабатывается и не сохраняется |

Статус `overdue` не хранится в БД, а вычисляется на лету: событие просрочено, если его `starts_at`
в прошлом и статус не `done`/`cancelled` (`app/api/events.py`).

## Возможности MVP

- профиль и несколько питомцев, фото, случайная публичная ссылка медкарты;
- календарь прививок и обработок с вычисляемым статусом `overdue`;
- SSE-чат с Ollama, персональным системным контекстом и очисткой истории;
- локальная демонстрация уведомления на странице календаря (Web Notification API, нужно разрешение браузера);
- демо-тарифы Plus: данные карт не отправляются и не сохраняются;
- PWA: manifest с иконками (генератор — `frontend/scripts/generate-icons.py`) и service worker,
  который кэширует только оболочку приложения. Запросы к `/api/` и `/uploads/` не кэшируются никогда:
  это персональные данные. Регистрация service worker включается только в production-сборке —
  в dev-режиме он ломает горячую перезагрузку.

## Структура проекта

```
.github/workflows/  CI: линтер, тесты, сборка и проверка контейнеров
backend/
  app/api/          роутеры: pets, events, chat, payments, health
  app/models/       SQLAlchemy-модели (pets, calendar_events, chat_messages, subscriptions)
  app/schemas/      Pydantic-схемы
  app/services/     демо-платежи
  app/seed.py       сидер демо-данных
  alembic/          миграции
  tests/            pytest: API, доступы, публичная медкарта, деградация чата
frontend/
  public/           manifest, service worker, иконки PWA
  scripts/          генератор иконок
  src/pages/        HomePage, DashboardPage, PetPage, CalendarPage, ChatPage, PlusPage, MedicalCardPage
  src/components/   Layout, PetSwitcher, DogIllustration
  src/context/      PetContext (активный питомец)
  src/lib/          api.ts, types.ts, format.ts, registerServiceWorker.ts
```

## Скриншоты

Основной dashboard содержит bento-сетку с приветствием, карточками прививки, веса, ИИ и Plus. В браузере можно проверить мобильный режим на ширинах 375/768/1024/1440/1920 px.

## Если что-то не запускается

**`sh: vite: Permission denied`, контейнер frontend выходит с кодом 126.**
В образ попал `node_modules`, собранный на macOS (там бинарники `darwin-arm64` и нет флага `+x`),
и `COPY . .` затёр linux-пакеты, установленные `npm install`. В проекте есть `frontend/.dockerignore`
с `node_modules` — не удаляйте его и не переносите `node_modules` между системами. Лечение:

```bash
docker compose -p petspace up -d --build frontend
```

**Страница `/app` отдаёт 500, в логах `EISDIR: illegal operation on a directory, read /app`.**
Рабочая папка контейнера совпала с маршрутом SPA. В `frontend/Dockerfile` должно быть
`WORKDIR /usr/src/app` (не `/app`).

**В кабинете нет питомцев.** Не выполнен сидер:
`docker compose -p petspace exec backend python -m app.seed`.

**Чат отвечает ошибкой или молчит.** Проверьте `ollama pull qwen2.5:3b`,
`curl http://localhost:11434/api/tags` и `brew services list` (там `ollama` должен быть `started`);
из контейнера адрес должен быть `host.docker.internal:11434`.

**Порты заняты.** 5173/8000 меняются в `docker-compose.yml`, порт БД — переменной `POSTGRES_PORT`
в `.env`. Занявший процесс ищется так: `lsof -i :5173`.

**`FATAL: role "petspace" does not exist` при запуске backend на хосте.** Вы попали в локальный
Postgres на 5432, а не в контейнерный: используйте `localhost:5433` (`POSTGRES_PORT`).

**Таблиц нет / ошибки миграций.** `docker compose -p petspace exec backend alembic upgrade head`.
