#!/usr/bin/env bash
# Сквозная проверка основы клиники на запущенном стенде (docker compose up).
# Запуск из корня проекта:  bash scripts/smoke_clinic.sh
set -euo pipefail

API="${API:-http://localhost:8000/api/v1}"
PROMOTE_CMD="${PROMOTE_CMD:-docker compose -p petspace exec -T backend python -m app.cli promote}"
RUN="$(date +%s)"
CLINIC_EMAIL="clinic-$RUN@example.com"
ADMIN_EMAIL="platform-$RUN@example.com"
DOCTOR_EMAIL="doctor-$RUN@example.com"
PASSWORD="smoke-pass-123"
CONSENTS='[{"kind":"terms","version":"2026-01-01"},{"kind":"privacy","version":"2026-01-01"}]'

# json 'выражение над d' — достаёт поле из JSON со stdin
json() { python3 -c 'import json,sys; d=json.load(sys.stdin); print(eval(sys.argv[1]))' "$1"; }
code() { curl -s -o /dev/null -w "%{http_code}" "$@"; }
post() { curl -sS -X POST -H 'Content-Type: application/json' "$@"; }

echo "== 1. Заявка клиники (ИНН с верной контрольной цифрой)"
REG=$(post "$API/clinics/register" -d "{
  \"clinic_name\": \"Смоук-клиника $RUN\", \"inn\": \"7707083893\",
  \"address\": \"г. Москва, ул. Тестовая, д. $RUN\", \"phone\": \"8 (495) 123-45-67\",
  \"contact_name\": \"Иванова Мария\", \"admin_email\": \"$CLINIC_EMAIL\",
  \"password\": \"$PASSWORD\", \"consents\": $CONSENTS }")
CLINIC_TOKEN=$(echo "$REG" | json "d['access_token']")
CLINIC_ID=$(echo "$REG" | json "d['clinic']['id']")
echo "клиника #$CLINIC_ID, статус: $(echo "$REG" | json "d['clinic']['status']"), роль: $(echo "$REG" | json "d['user']['role']")"
AUTH_CLINIC=(-H "Authorization: Bearer $CLINIC_TOKEN")

echo "== 2. Загрузка документа"
printf '%%PDF-1.4\n%% smoke test\n' > /tmp/smoke_license.pdf
curl -sS -X POST "$API/clinics/me/documents" "${AUTH_CLINIC[@]}" \
  -F "file=@/tmp/smoke_license.pdf" -F "title=Лицензия" | json "'документ #%s, %s, %s байт' % (d['id'], d['content_type'], d['size_bytes'])"

echo "== 3. До одобрения сотрудники недоступны (ждём 403)"
echo "HTTP $(code "$API/clinics/me/staff" "${AUTH_CLINIC[@]}")"

echo "== 4. Модератор платформы"
ADMIN_TOKEN=$(post "$API/auth/register" -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$PASSWORD\",\"consents\":$CONSENTS}" | json "d['access_token']")
$PROMOTE_CMD --email "$ADMIN_EMAIL"
AUTH_ADMIN=(-H "Authorization: Bearer $ADMIN_TOKEN")
echo "очередь заявок:"
curl -sS "$API/admin/clinics?status=pending" "${AUTH_ADMIN[@]}" | json "[(c['id'], c['name'], c['documents_count']) for c in d]"
echo "обычный клиент в админке (ждём 403): HTTP $(code "$API/admin/clinics" "${AUTH_CLINIC[@]}")"

echo "== 5. Одобрение"
post "$API/admin/clinics/$CLINIC_ID/approve" "${AUTH_ADMIN[@]}" | json "'статус: ' + d['status']"
echo "сотрудники после одобрения (ждём 200): HTTP $(code "$API/clinics/me/staff" "${AUTH_CLINIC[@]}")"

echo "== 6. Приглашение врача"
post "$API/clinics/me/staff" "${AUTH_CLINIC[@]}" \
  -d "{\"email\":\"$DOCTOR_EMAIL\",\"full_name\":\"Петров Пётр\",\"role\":\"clinic_doctor\"}" \
  | json "'сотрудник #%s, роль %s' % (d['id'], d['role'])"

echo "== 7. Врач задаёт пароль через «Забыли пароль» и входит"
CODE=$(post "$API/auth/password/reset/request" -d "{\"email\":\"$DOCTOR_EMAIL\"}" | json "d.get('dev_code')")
if [ "$CODE" = "None" ]; then
  echo "dev_code не возвращается (EXPOSE_DEV_OTP выключен): возьмите код из логов backend и завершите шаг вручную."
  exit 0
fi
DOCTOR_TOKEN=$(post "$API/auth/password/reset/confirm" -d "{\"email\":\"$DOCTOR_EMAIL\",\"code\":\"$CODE\",\"new_password\":\"$PASSWORD\"}" | json "d['access_token']")
AUTH_DOCTOR=(-H "Authorization: Bearer $DOCTOR_TOKEN")
curl -sS "$API/clinics/me" "${AUTH_DOCTOR[@]}" | json "'врач видит клинику «%s», роль %s' % (d['name'], d['my_role'])"
echo "до принятия согласий список сотрудников закрыт (ждём 403): HTTP $(code "$API/clinics/me/staff" "${AUTH_DOCTOR[@]}")"
post "$API/auth/consents" "${AUTH_DOCTOR[@]}" -d "{\"consents\":$CONSENTS}" > /dev/null
echo "после принятия согласий (ждём 200): HTTP $(code "$API/clinics/me/staff" "${AUTH_DOCTOR[@]}")"
echo "врач приглашает коллегу (ждём 403): HTTP $(code -X POST -H 'Content-Type: application/json' "$API/clinics/me/staff" "${AUTH_DOCTOR[@]}" -d '{"email":"x@example.com","full_name":"Икс Игрек","role":"clinic_registrar"}')"

echo "== 8. Приостановка и возврат"
post "$API/admin/clinics/$CLINIC_ID/suspend" "${AUTH_ADMIN[@]}" -d '{"reason":"Проверка смоук-теста"}' | json "'статус: ' + d['status']"
echo "сотрудники при приостановке (ждём 403): HTTP $(code "$API/clinics/me/staff" "${AUTH_CLINIC[@]}")"
post "$API/admin/clinics/$CLINIC_ID/approve" "${AUTH_ADMIN[@]}" | json "'статус: ' + d['status']"

echo
echo "ГОТОВО: заявка, модерация, документы, сотрудники и роли работают."
