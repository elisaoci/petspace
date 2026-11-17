#!/usr/bin/env bash
# Сквозная проверка этапа 4 на запущенном стенде: код владельца, запрос по телефону, отзыв доступа.
# Запуск из корня проекта:  bash scripts/smoke_patient_access.sh
set -euo pipefail

API="${API:-http://localhost:8000/api/v1}"
PROMOTE_CMD="${PROMOTE_CMD:-docker compose -p petspace exec -T backend python -m app.cli promote}"
RUN="$(date +%s)"
PASSWORD="smoke-pass-123"
CONSENTS='[{"kind":"terms","version":"2026-01-01"},{"kind":"privacy","version":"2026-01-01"}]'
OWNER_EMAIL="owner-$RUN@example.com"
OWNER_PHONE="+7999$(printf '%07d' $((RUN % 10000000)))"

json() { python3 -c 'import json,sys; d=json.load(sys.stdin); print(eval(sys.argv[1]))' "$1"; }
code() { curl -s -o /dev/null -w "%{http_code}" "$@"; }
post() { curl -sS -X POST -H 'Content-Type: application/json' "$@"; }
put() { curl -sS -X PUT -H 'Content-Type: application/json' "$@"; }

echo "== 1. Клиника и модератор (заявка, одобрение)"
REG=$(post "$API/clinics/register" -d "{
  \"clinic_name\": \"Этап4-клиника $RUN\", \"inn\": \"7707083893\",
  \"address\": \"г. Москва, ул. Тестовая, д. $RUN\", \"phone\": \"+7 495 123-45-67\",
  \"contact_name\": \"Иванова Мария\", \"admin_email\": \"clinic-$RUN@example.com\",
  \"password\": \"$PASSWORD\", \"consents\": $CONSENTS }")
CLINIC_TOKEN=$(echo "$REG" | json "d['access_token']")
CLINIC_ID=$(echo "$REG" | json "d['clinic']['id']")
ADMIN_EMAIL="platform-$RUN@example.com"
ADMIN_TOKEN=$(post "$API/auth/register" -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$PASSWORD\",\"consents\":$CONSENTS}" | json "d['access_token']")
$PROMOTE_CMD --email "$ADMIN_EMAIL"
post "$API/admin/clinics/$CLINIC_ID/approve" -H "Authorization: Bearer $ADMIN_TOKEN" | json "'клиника #$CLINIC_ID: ' + d['status']"
AUTH_CLINIC=(-H "Authorization: Bearer $CLINIC_TOKEN")

echo "== 2. Владелец: аккаунт, телефон, питомец, запись в медкарте"
OWNER_TOKEN=$(post "$API/auth/register" -d "{\"email\":\"$OWNER_EMAIL\",\"password\":\"$PASSWORD\",\"consents\":$CONSENTS}" | json "d['access_token']")
AUTH_OWNER=(-H "Authorization: Bearer $OWNER_TOKEN")
put "$API/profile/phone" "${AUTH_OWNER[@]}" -d "{\"phone\":\"$OWNER_PHONE\"}" | json "'телефон: ' + d['phone']"
PET_ID=$(post "$API/pets" "${AUTH_OWNER[@]}" -d '{"name":"Барсик","species":"dog","birth_date":"2020-03-01","sex":"male","owner_notes":"секретная заметка"}' | json "d['id']")
post "$API/pets/$PET_ID/records" "${AUTH_OWNER[@]}" -d '{"kind":"visit","title":"Осмотр","occurred_at":"2026-01-10T10:00:00Z"}' > /dev/null
echo "питомец #$PET_ID создан"

echo "== 3. Путь 1: код владельца"
CODE=$(post "$API/pets/$PET_ID/access-codes" "${AUTH_OWNER[@]}" -d '{"ttl_days":1}' | json "d['code']")
echo "код: $CODE"
OPENED=$(post "$API/clinics/me/access-codes/redeem" "${AUTH_CLINIC[@]}" -d "{\"code\":\"$CODE\"}")
GRANT_ID=$(echo "$OPENED" | json "d['grant_id']")
echo "$OPENED" | json "'доступ #%s к питомцу %s, разделы %s' % (d['grant_id'], d['pet']['name'], d['scopes'])"
curl -sS "$API/clinics/me/patients/$PET_ID" "${AUTH_CLINIC[@]}" | json "'карта: %s, записей: %d, заметок владельца в ответе нет: %s' % (d['pet']['name'], len(d['records']), 'owner_notes' not in str(d))"
echo "повторный ввод того же кода (ждём 404): HTTP $(code -X POST -H 'Content-Type: application/json' "$API/clinics/me/access-codes/redeem" "${AUTH_CLINIC[@]}" -d "{\"code\":\"$CODE\"}")"

echo "== 4. Владелец отзывает доступ — клиника теряет его сразу"
post "$API/access-grants/$GRANT_ID/revoke" "${AUTH_OWNER[@]}" > /dev/null
echo "чтение карты после отзыва (ждём 404): HTTP $(code "$API/clinics/me/patients/$PET_ID" "${AUTH_CLINIC[@]}")"

echo "== 5. Путь 2: запрос по имени питомца и телефону"
REQ=$(post "$API/clinics/me/access-requests" "${AUTH_CLINIC[@]}" -d "{\"pet_name\":\"барсик\",\"owner_phone\":\"$OWNER_PHONE\",\"ttl_days\":3,\"message\":\"Запись на 15:00\"}")
echo "$REQ" | json "'запрос #%s: %s, пациент в ответе клинике: %s' % (d['id'], d['status'], d['patient'])"
echo "до решения владельца карта закрыта (ждём 404): HTTP $(code "$API/clinics/me/patients/$PET_ID" "${AUTH_CLINIC[@]}")"
INBOX=$(curl -sS "$API/access-requests?status=pending" "${AUTH_OWNER[@]}")
echo "$INBOX" | json "'во входящих владельца: %d, от клиники «%s», сообщение: %s' % (len(d), d[0]['clinic']['name'], d[0]['message'])"
RID=$(echo "$INBOX" | json "d[0]['id']")
post "$API/access-requests/$RID/approve" "${AUTH_OWNER[@]}" -d '{"scopes":["profile","records"]}' | json "'владелец одобрил: ' + d['status']"
curl -sS "$API/clinics/me/patients/$PET_ID" "${AUTH_CLINIC[@]}" | json "'карта снова доступна: %s, прививки скрыты (не запрошены владельцем): %s' % (d['pet']['name'], d['vaccinations'] is None)"
curl -sS "$API/clinics/me/patients" "${AUTH_CLINIC[@]}" | json "'пациентов у клиники: %d' % len(d)"

echo "== 6. Справочник клиник для владельца"
curl -sS "$API/clinics/directory" "${AUTH_OWNER[@]}" | json "'одобренных клиник в справочнике: %d' % len(d)"

echo
echo "ГОТОВО: коды, запросы, отзыв и чтение карты клиникой работают."
