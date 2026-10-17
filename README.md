# PetSpace

Сайт для профиля питомца, календаря здоровья, локального ИИ-помощника и демо-подписки PetSpace Plus.

- Frontend: React 18 + TypeScript, Vite 5, React Router 6, Tailwind CSS — порт **5173**
- Backend: FastAPI + SQLAlchemy 2.0 + Alembic — порт **8000**, API на `/api/v1`, Swagger на `/docs`
- БД: PostgreSQL 16 — внутри compose `db:5432`, на хост публикуется как **5433** (`POSTGRES_PORT`)
- Авторизация: вход по одноразовому коду на email, JWT access + refresh с ротацией
- ИИ: Ollama на хосте (по умолчанию модель `qwen2.5:3b`), ответы стримятся по SSE

Страницы: `/` главная, `/login` вход, `/app` кабинет, `/app/pet`, `/app/calendar`, `/app/chat`,
`/plus`, `/medical/:token`.

## Быстрый старт (Docker Compose)

```bash
cp .env.example .env
docker compose -p petspace up -d --build
```

Откройте http://localhost:5173 (Swagger — http://localhost:8000/docs), зарегистрируйтесь на вкладке
«Регистрация» — аккаунт создаётся обычным путём и хранится в базе.

Потом наполните аккаунт демо-данными (питомец «Макс» и два события календаря):

```bash
docker compose -p petspace exec backend python -m app.seed
```

Сидер **не создаёт пользователей и не знает паролей**: если в базе один аккаунт — данные достанутся
ему, если несколько — укажите явно `python -m app.seed --email you@example.com`.

Флаг `-d` обязателен, если вы не хотите держать терминал занятым: без него `Ctrl+C` останавливает контейнеры.

Миграции Alembic применяются автоматически: в `docker-compose.yml` backend запускается командой
`alembic upgrade head && uvicorn app.main:app ...` и ждёт healthcheck базы. Сидер заодно привязывает
к аккаунту питомцев, оставшихся без владельца с ранних версий.

**Код монтируется в контейнеры** (`./backend:/app`, `./frontend:/usr/src/app`), поэтому правки
применяются сами: backend перезапускается `uvicorn --reload`, frontend — dev-сервером Vite.
Пересобирать образы нужно только при изменении зависимостей (`requirements.txt`, `package.json`):

```bash
docker compose -p petspace up -d --build
```

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
что заметки владельца в неё не попадают и что перевыпуск токена ломает старую ссылку), деградацию
чата при недоступной модели, а также авторизацию целиком: вход по коду, лимиты попыток, ротацию
refresh-токенов, обнаружение повторного использования токена, требование согласий и изоляцию
владельцев (чужой питомец, его события и чат недоступны). Frontend проверяется типами при сборке —
`npm run build`.

## CI

`.github/workflows/ci.yml` запускается на каждый push в `main` и на pull request:

- **backend** — `ruff check` и `pytest` с сервисным PostgreSQL;
- **frontend** — `npm ci` и `npm run build`;
- **docker** — сборка обоих образов, запуск frontend-контейнера и проверка, что `/`, `/app` и `/plus`
  отвечают 200. Это регрессия на два уже исправленных бага: `vite: Permission denied`
  (node_modules с macOS в образе) и конфликт `WORKDIR /app` с маршрутом SPA `/app`.

## Авторизация

Два способа входа для владельца: **пароль** (основной) и **одноразовый код на email** (запасной,
он же основа для будущего восстановления пароля).

1. **Регистрация** — `POST /api/v1/auth/register` с `{"email", "password", "consents"}`.
   Пароль от 8 символов, согласия обязательны: без них аккаунт не создаётся (ответ `422`
   `consent_required`). Повторная регистрация на тот же адрес — `409 email_taken`.
   Актуальные версии согласий отдаёт `GET /api/v1/auth/consents/required`, поэтому фронтенд
   не дублирует юридические тексты у себя.
2. **Вход** — `POST /api/v1/auth/login` с `{"email", "password"}`. Ответ на неверный пароль и на
   несуществующий email одинаковый, чтобы нельзя было перебрать адреса. После 5 неудачных попыток
   аккаунт блокируется на 15 минут (`429` + `Retry-After`).
3. **Вход по коду** — `POST /api/v1/auth/otp/request` (код из 6 цифр, 5 минут, не больше 3 запросов
   в час) и `POST /api/v1/auth/otp/verify`. Код создаёт сессию только для существующего аккаунта:
   регистрация здесь невозможна, неизвестный адрес получает `404 user_not_found`.
4. Дальше access-токен идёт в заголовке `Authorization: Bearer <token>`.

Особенности реализации:

- **Пароли.** PBKDF2-HMAC-SHA256, 600 000 итераций, случайная соль; в БД лежит
  `pbkdf2_sha256$итерации$соль$хэш`, поэтому переход на Argon2id не потребует сброса паролей.
- **Почты пока нет.** Провайдер не подключён: письмо печатается в лог backend
  (`docker compose -p petspace logs -f backend`), а вне `ENVIRONMENT=prod` код дополнительно
  возвращается полем `dev_code`. В prod этого поля не будет.
- **Токены.** Access живёт 15 минут, refresh — 30 дней и одноразовый. Каждый `/auth/refresh` гасит
  старый токен и выдаёт новый; повторное использование старого токена считается кражей и отзывает
  все сессии (событие `auth.refresh.reuse_detected` в журнале).
- **Хранение.** В БД только хэши: пароли — PBKDF2, refresh-токены — SHA-256, коды входа —
  HMAC-SHA256 с секретом приложения.
- **Согласия** хранятся с датой и версией текста. Создание питомца требует актуальных согласий,
  иначе `403` с `consent_required`.
- **Доступ к данным.** Любой запрос без токена — `401`. Чужой питомец, его события и история чата
  возвращают `404` (а не `403`), чтобы нельзя было выяснить существование чужой карточки.
- **Аудит.** В `audit_logs` попадают регистрация, входы и неудачные попытки, ротация и кража токенов,
  обращения к публичной медкарте, удаление питомца и перевыпуск ссылки медкарты.
- **Секретов в логах нет.** Пароли не печатаются нигде: ни в сидере, ни в логах, ни в ответах API.
  Код входа отдаётся в ответе API лишь при `EXPOSE_DEV_OTP=true` (локальная разработка), а в prod
  конфигурация с этим флагом просто не запустится.

Пример через curl (регистрация нового аккаунта и запрос питомцев):

```bash
API=http://localhost:8000/api/v1
ACCESS=$(curl -s -X POST $API/auth/register -H 'Content-Type: application/json' \
  -d '{"email":"me@example.com","password":"strong-pass-1",
       "consents":[{"kind":"terms","version":"2026-01-01"},
                   {"kind":"privacy","version":"2026-01-01"}]}' \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])")
curl -s -H "Authorization: Bearer $ACCESS" $API/pets
```

## Переменные окружения

| Переменная | Назначение | Значение по умолчанию |
| --- | --- | --- |
| `DATABASE_URL` | строка подключения SQLAlchemy | `postgresql+psycopg://petspace:petspace@localhost:5432/petspace` |
| `POSTGRES_PORT` | порт Postgres **на хосте** (внутри compose всегда `db:5432`) | `5432`, в `.env.example` — `5433` |
| `ENVIRONMENT` | `dev`, `staging` или `prod`; в prod запрещены небезопасные значения по умолчанию | `dev` |
| `JWT_SECRET` | секрет для подписи токенов и HMAC кодов; в prod обязателен и не короче 32 символов | `dev-insecure-change-me` |
| `ACCESS_TOKEN_TTL_MINUTES` | срок жизни access-токена | `15` |
| `REFRESH_TOKEN_TTL_DAYS` | срок жизни refresh-токена | `30` |
| `PASSWORD_ITERATIONS` | число итераций PBKDF2 | `600000` |
| `LOGIN_MAX_ATTEMPTS` | неудачных входов до блокировки | `5` |
| `LOGIN_LOCKOUT_MINUTES` | длительность блокировки | `15` |
| `OTP_TTL_MINUTES` | срок жизни кода входа | `5` |
| `OTP_MAX_ATTEMPTS` | попыток ввода одного кода | `5` |
| `OTP_MAX_REQUESTS_PER_HOUR` | запросов кода на адрес в час | `3` |
| `EMAIL_SENDER` | способ отправки писем; `console` пишет в лог | `console` |
| `EXPOSE_DEV_OTP` | отдавать код входа в ответе API (только локальная разработка; в prod запрещено) | `false` |
| `OLLAMA_BASE_URL` | адрес Ollama | `http://localhost:11434` |
| `OLLAMA_MODEL` | модель для чата | `qwen2.5:3b` |
| `VITE_API_URL` | база API для фронтенда | `http://localhost:8000/api/v1` |
| `UPLOAD_DIR` | папка загруженных фото | `uploads` |

Почему на хосте `5433`: на 5432 часто уже слушает локальный Postgres/Postgres.app, и тогда
подключение с хоста перехватывает он — появляется `FATAL: role "petspace" does not exist`, хотя в
контейнере всё в порядке. Порт меняется одной строкой в `.env`, сеть контейнеров не затрагивается:
backend всегда ходит на `db:5432`.

## API

| Метод | Путь | Что делает |
| --- | --- | --- |
| GET | `/api/health`, `/api/v1/health` | статус сервиса, БД и имя модели (без авторизации) |
| POST | `/api/v1/auth/register` | регистрация: email, пароль, обязательные согласия |
| POST | `/api/v1/auth/login` | вход по email и паролю |
| POST | `/api/v1/auth/otp/request` | отправка кода входа на email |
| POST | `/api/v1/auth/otp/verify` | вход по коду (только для существующего аккаунта) |
| POST | `/api/v1/auth/refresh` | ротация refresh-токена |
| POST | `/api/v1/auth/logout` | отзыв refresh-токена |
| GET | `/api/v1/auth/me` | текущий пользователь и статус согласий |
| GET | `/api/v1/auth/consents/required` | актуальные версии текстов согласий |
| POST | `/api/v1/auth/consents` | принять согласия отдельным запросом |
| GET/POST | `/api/v1/pets` | список (только свои) и создание питомцев |
| GET/PATCH/DELETE | `/api/v1/pets/{id}` | карточка питомца |
| POST | `/api/v1/pets/{id}/photo` | загрузка фото (jpg, jpeg, png, webp) |
| POST | `/api/v1/pets/{id}/medical-token` | перевыпуск секретной ссылки медкарты |
| GET | `/api/v1/pets/public/medical-card/{token}` | публичная медкарта без заметок владельца (без авторизации) |
| GET/POST | `/api/v1/events` | календарь (фильтр `?pet_id=`), у каждого события есть `computed_status` |
| GET/PATCH/DELETE | `/api/v1/events/{id}` | редактирование события |
| POST | `/api/v1/chat/stream` | SSE-поток ответа Ollama с контекстом питомца |
| GET/DELETE | `/api/v1/chat/history/{conversation_id}` | история и очистка диалога |
| POST | `/api/v1/payments/demo` | заглушка демо-оплаты: карта не обрабатывается и не сохраняется |

Всё, кроме `health` и публичной медкарты, требует заголовок `Authorization: Bearer <access_token>`.

Статус `overdue` не хранится в БД, а вычисляется на лету: событие просрочено, если его `starts_at`
в прошлом и статус не `done`/`cancelled` (`app/api/events.py`).

## Возможности MVP

- вход владельца по одноразовому коду, согласия с версиями текста и журнал доступа к данным;
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
  app/api/          роутеры: auth, pets, events, chat, payments, health; deps.py — доступ и роли
  app/models/       модели: entities.py (питомцы, календарь, чат), auth.py (пользователи, OTP, токены, согласия, аудит)
  app/schemas/      Pydantic-схемы
  app/services/     security (JWT/OTP), sessions (ротация токенов), consents, email, audit, демо-платежи
  app/seed.py       сидер демо-данных
  alembic/          миграции
  tests/            pytest: API, авторизация, изоляция владельцев, публичная медкарта, чат
frontend/
  public/           manifest, service worker, иконки PWA
  scripts/          генератор иконок
  src/pages/        HomePage, LoginPage, DashboardPage, PetPage, CalendarPage, ChatPage, PlusPage, MedicalCardPage
  src/components/   Layout, PetSwitcher, DogIllustration, RequireAuth
  src/context/      AuthContext (сессия), PetContext (активный питомец)
  src/lib/          api.ts (токены и автообновление), types.ts, format.ts, registerServiceWorker.ts
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
`docker compose -p petspace exec backend python -m app.seed` (нужен уже зарегистрированный аккаунт).

**Сидер пишет «В базе нет пользователей».** Это нормально: сидер не создаёт аккаунты. Зарегистрируйтесь
на `/login` и запустите его снова; если аккаунтов несколько — укажите `--email you@example.com`.

**Кабинет просит войти или API отвечает 401.** Это ожидаемо: без токена доступ закрыт.
Войдите на `/login` своим email и паролем.

**Пароль не подходит.** Восстановления пока нет: используйте «Войти по коду с почты».

**Код входа не приходит на почту.** Почтовый провайдер ещё не подключён: `EMAIL_SENDER=console`
печатает письмо в лог backend, а при `EXPOSE_DEV_OTP=true` код дополнительно виден на экране входа.

**Чат отвечает ошибкой или молчит.** Проверьте `ollama pull qwen2.5:3b`,
`curl http://localhost:11434/api/tags` и `brew services list` (там `ollama` должен быть `started`);
из контейнера адрес должен быть `host.docker.internal:11434`.

**Порты заняты.** 5173/8000 меняются в `docker-compose.yml`, порт БД — переменной `POSTGRES_PORT`
в `.env`. Занявший процесс ищется так: `lsof -i :5173`.

**`FATAL: role "petspace" does not exist` при запуске backend на хосте.** Вы попали в локальный
Postgres на 5432, а не в контейнерный: используйте `localhost:5433` (`POSTGRES_PORT`).

**Таблиц нет / ошибки миграций.** `docker compose -p petspace exec backend alembic upgrade head`.
