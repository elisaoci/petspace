#!/usr/bin/env bash
# Сквозная проверка этапа 5 на запущенном стенде: приём, записи врача, правка, файл, завершение.
# Запуск из корня проекта:  bash scripts/smoke_encounters.sh
set -euo pipefail

API="${API:-http://localhost:8000/api/v1}"
PROMOTE_CMD="${PROMOTE_CMD:-docker compose -p petspace exec -T backend python -m app.cli promote}"
RUN="$(date +%s)"
PASSWORD="smoke-pass-123"
CONSENTS='[{"kind":"terms","version":"2026-01-01"},{"kind":"privacy","version":"2026-01-01"}]'
OWNER_PHONE="+7999$(printf '%07d' $((RUN % 10000000)))"

json() { python3 -c 'import json,sys; d=json.load(sys.stdin); print(eval(sys.argv[1]))' "$1"; }
code() { curl -s -o /dev/null -w "%{http_code}" "$@"; }
post() { curl -sS -X POST -H 'Content-Type: application/json' "$@"; }
put() { curl -sS -X PUT -H 'Content-Type: application/json' "$@"; }
patch() { curl -sS -X PATCH -H 'Content-Type: application/json' "$@"; }

echo "== 1. Клиника, модератор, владелец с питомцем"
REG=$(post "$API/clinics/register" -d "{
  \"clinic_name\": \"Этап5-клиника $RUN\", \"inn\": \"7707083893\",
  \"address\": \"г. Москва, ул. Тестовая, д. $RUN\", \"phone\": \"+7 495 123-45-67\",
  \"contact_name\": \"Иванова Мария\", \"admin_email\": \"clinic-$RUN@example.com\",
  \"password\": \"$PASSWORD\", \"consents\": $CONSENTS }")
CLINIC_TOKEN=$(echo "$REG" | json "d['access_token']")
CLINIC_ID=$(echo "$REG" | json "d['clinic']['id']")
ADMIN_EMAIL="platform-$RUN@example.com"
ADMIN_TOKEN=$(post "$API/auth/register" -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$PASSWORD\",\"consents\":$CONSENTS}" | json "d['access_token']")
$PROMOTE_CMD --email "$ADMIN_EMAIL"
post "$API/admin/clinics/$CLINIC_ID/approve" -H "Authorization: Bearer $ADMIN_TOKEN" > /dev/null
AUTH_CLINIC=(-H "Authorization: Bearer $CLINIC_TOKEN")

OWNER_TOKEN=$(post "$API/auth/register" -d "{\"email\":\"owner-$RUN@example.com\",\"password\":\"$PASSWORD\",\"consents\":$CONSENTS}" | json "d['access_token']")
AUTH_OWNER=(-H "Authorization: Bearer $OWNER_TOKEN")
put "$API/profile/phone" "${AUTH_OWNER[@]}" -d "{\"phone\":\"$OWNER_PHONE\"}" > /dev/null
PET_ID=$(post "$API/pets" "${AUTH_OWNER[@]}" -d '{"name":"Барсик","species":"dog","birth_date":"2020-03-01","sex":"male"}' | json "d['id']")
CODE=$(post "$API/pets/$PET_ID/access-codes" "${AUTH_OWNER[@]}" -d '{}' | json "d['code']")
GRANT_ID=$(post "$API/clinics/me/access-codes/redeem" "${AUTH_CLINIC[@]}" -d "{\"code\":\"$CODE\"}" | json "d['grant_id']")
echo "клиника #$CLINIC_ID, питомец #$PET_ID, доступ #$GRANT_ID открыт по коду $CODE"

echo "== 2. Врач начинает приём"
ENC=$(post "$API/clinics/me/patients/$PET_ID/encounters" "${AUTH_CLINIC[@]}")
ENC_ID=$(echo "$ENC" | json "d['id']")
echo "$ENC" | json "'приём #%s: %s, врач %s' % (d['id'], d['status'], d['doctor_name'])"
echo "второй приём по тому же питомцу (ждём 409): HTTP $(code -X POST "$API/clinics/me/patients/$PET_ID/encounters" "${AUTH_CLINIC[@]}")"

echo "== 3. Записи: осмотр, назначение, прививка"
VISIT=$(post "$API/clinics/me/encounters/$ENC_ID/records" "${AUTH_CLINIC[@]}" \
  -d '{"kind":"visit","title":"Осмотр","description":"Кашель второй день","diagnosis":"ОРВИ"}')
VISIT_ID=$(echo "$VISIT" | json "d['id']")
echo "$VISIT" | json "'запись #%s от клиники «%s», автор: %s' % (d['id'], d['clinic_name'], d['author_name'])"
post "$API/clinics/me/encounters/$ENC_ID/records" "${AUTH_CLINIC[@]}" -d '{"kind":"prescription","title":"Сироп от кашля, 5 мл 2 раза в день"}' > /dev/null
post "$API/clinics/me/encounters/$ENC_ID/records" "${AUTH_CLINIC[@]}" -d '{"kind":"vaccination","title":"Бешенство"}' > /dev/null
echo "записей в приёме: $(curl -sS "$API/clinics/me/encounters/$ENC_ID" "${AUTH_CLINIC[@]}" | json "len(d['records'])")"

echo "== 4. Правка с сохранением истории и вложение"
patch "$API/clinics/me/records/$VISIT_ID" "${AUTH_CLINIC[@]}" -d '{"diagnosis":"Трахеит"}' | json "'диагноз теперь: ' + d['diagnosis']"
printf '%%PDF-1.4\n%% smoke test\n' > /tmp/smoke_lab.pdf
curl -sS -X POST "$API/clinics/me/records/$VISIT_ID/attachments" "${AUTH_CLINIC[@]}" -F "file=@/tmp/smoke_lab.pdf" \
  | json "'файл #%s: %s, %s, %s байт' % (d['id'], d['filename'], d['content_type'], d['size_bytes'])"

echo "== 5. Завершение приёма"
post "$API/clinics/me/encounters/$ENC_ID/finish" "${AUTH_CLINIC[@]}" | json "'статус: %s, длительность: %s с' % (d['status'], d['duration_seconds'])"
echo "запись после завершения (ждём 409): HTTP $(code -X POST -H 'Content-Type: application/json' "$API/clinics/me/encounters/$ENC_ID/records" "${AUTH_CLINIC[@]}" -d '{"title":"Поздно"}')"

echo "== 6. Что видит владелец"
curl -sS "$API/pets/$PET_ID/records" "${AUTH_OWNER[@]}" | json "'записей в медкарте: %d, от клиники: %d' % (len(d), len([r for r in d if r['author_type']=='clinic']))"
curl -sS "$API/records/$VISIT_ID/revisions" "${AUTH_OWNER[@]}" | json "'история записи: %s' % [r['action'] for r in d]"
curl -sS "$API/records/$VISIT_ID/attachments" "${AUTH_OWNER[@]}" | json "'файлов у записи: %d' % len(d)"

echo "== 7. Владелец отзывает доступ — запись закрыта сразу"
post "$API/access-grants/$GRANT_ID/revoke" "${AUTH_OWNER[@]}" > /dev/null
echo "правка после отзыва (ждём 404): HTTP $(code -X PATCH -H 'Content-Type: application/json' "$API/clinics/me/records/$VISIT_ID" "${AUTH_CLINIC[@]}" -d '{"diagnosis":"X"}')"

echo
echo "ГОТОВО: приём, записи врача, правка с историей, вложения и завершение работают."
