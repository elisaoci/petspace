"""Авторизация владельца: вход по одноразовому коду на email, JWT и согласия."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession
from app.config import get_settings
from app.models import (
    CONSENT_VERSIONS,
    ROLE_OWNER,
    STATUS_ACTIVE,
    OtpCode,
    User,
)
from app.schemas.auth import (
    ConsentRequirement,
    ConsentsPayload,
    OtpRequestPayload,
    OtpRequestResponse,
    OtpVerifyPayload,
    RefreshPayload,
    TokenPairResponse,
    UserResponse,
)
from app.services.audit import client_ip, record_audit
from app.services.consents import (
    missing_required_consents,
    record_consents,
    validate_consents,
)
from app.services.email import build_otp_message, get_email_sender
from app.services.security import (
    codes_equal,
    generate_otp_code,
    hash_otp,
)
from app.services.sessions import (
    REASON_REUSED,
    RefreshError,
    issue_token_pair,
    revoke_refresh_token,
    rotate_refresh_token,
)

router = APIRouter(prefix="/auth", tags=["auth"])

OTP_CHANNEL_EMAIL = "email"
OTP_PURPOSE_LOGIN = "login"


def _user_response(db: Session, user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        phone=user.phone,
        role=user.role,
        status=user.status,
        consents_accepted=not missing_required_consents(db, user.id),
        created_at=user.created_at,
    )


def _consent_pairs(payload: OtpVerifyPayload | ConsentsPayload) -> list[tuple[str, str]]:
    return [(item.kind, item.version) for item in payload.consents]


@router.post("/otp/request", response_model=OtpRequestResponse, status_code=status.HTTP_202_ACCEPTED)
def request_otp(payload: OtpRequestPayload, request: Request, db: DbSession) -> OtpRequestResponse:
    """Отправляет код входа. Ответ одинаковый для существующих и новых адресов:
    иначе по ответу API можно было бы узнать, есть ли у человека аккаунт."""
    settings = get_settings()
    now = datetime.now(UTC)
    destination = payload.email

    recent_requests = db.scalar(
        select(func.count())
        .select_from(OtpCode)
        .where(
            OtpCode.destination == destination,
            OtpCode.created_at >= now - timedelta(hours=1),
        )
    )
    if (recent_requests or 0) >= settings.otp_max_requests_per_hour:
        record_audit(
            db,
            action="otp.request.rate_limited",
            entity="otp",
            request=request,
            details={"destination": destination},
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Слишком много запросов кода. Попробуйте через час.",
        )

    code = generate_otp_code()
    db.add(
        OtpCode(
            channel=OTP_CHANNEL_EMAIL,
            destination=destination,
            purpose=OTP_PURPOSE_LOGIN,
            code_hash=hash_otp(code, settings.jwt_secret),
            expires_at=now + timedelta(minutes=settings.otp_ttl_minutes),
            request_ip=client_ip(request),
        )
    )
    db.commit()

    subject, text = build_otp_message(code, settings.otp_ttl_minutes)
    get_email_sender().send(destination, subject, text)
    record_audit(db, action="otp.request", entity="otp", request=request, details={"destination": destination})

    return OtpRequestResponse(
        message="Если адрес указан верно, код отправлен",
        expires_in=settings.otp_ttl_minutes * 60,
        dev_code=None if settings.is_production else code,
    )


@router.post("/otp/verify", response_model=TokenPairResponse)
def verify_otp(payload: OtpVerifyPayload, request: Request, db: DbSession) -> TokenPairResponse:
    settings = get_settings()
    now = datetime.now(UTC)
    destination = payload.email

    otp = db.scalar(
        select(OtpCode)
        .where(
            OtpCode.destination == destination,
            OtpCode.purpose == OTP_PURPOSE_LOGIN,
            OtpCode.consumed_at.is_(None),
        )
        .order_by(OtpCode.id.desc())
    )
    if otp is None or otp.expires_at <= now:
        record_audit(
            db,
            action="otp.verify.failure",
            entity="otp",
            request=request,
            details={"destination": destination, "reason": "no_active_code"},
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Код не найден или истёк, запросите новый")

    if otp.attempts >= settings.otp_max_attempts:
        record_audit(
            db,
            action="otp.verify.failure",
            entity="otp",
            request=request,
            details={"destination": destination, "reason": "too_many_attempts"},
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Слишком много попыток, запросите новый код",
        )

    if not codes_equal(otp.code_hash, hash_otp(payload.code.strip(), settings.jwt_secret)):
        otp.attempts += 1
        record_audit(
            db,
            action="otp.verify.failure",
            entity="otp",
            request=request,
            details={"destination": destination, "reason": "wrong_code", "attempts": otp.attempts},
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный код")

    user = db.scalar(select(User).where(User.email == destination))
    is_new_user = user is None

    # Проверяем согласия до любых изменений в БД: иначе неудачная попытка
    # израсходовала бы код и создала пользователя.
    consent_pairs = _consent_pairs(payload)
    if is_new_user and not consent_pairs:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "consent_required",
                "kinds": list(CONSENT_VERSIONS),
                "message": "Для регистрации нужно принять согласия",
            },
        )
    problems = validate_consents(consent_pairs)
    if problems:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "invalid_consents", "problems": problems},
        )

    otp.consumed_at = now
    if user is None:
        user = User(email=destination, role=ROLE_OWNER, status=STATUS_ACTIVE)
        db.add(user)
        db.flush()

    user.email_verified_at = user.email_verified_at or now
    user.last_login_at = now
    record_consents(db, user.id, consent_pairs, client_ip(request))

    access_token, refresh_token, expires_in = issue_token_pair(
        db,
        user,
        settings,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()
    db.refresh(user)

    record_audit(
        db,
        action="user.registered" if is_new_user else "auth.login",
        actor_user_id=user.id,
        entity="user",
        entity_id=user.id,
        request=request,
    )
    return TokenPairResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        user=_user_response(db, user),
    )


@router.post("/refresh", response_model=TokenPairResponse)
def refresh_tokens(payload: RefreshPayload, request: Request, db: DbSession) -> TokenPairResponse:
    settings = get_settings()
    try:
        user, access_token, refresh_token, expires_in = rotate_refresh_token(
            db,
            payload.refresh_token,
            settings,
            ip=client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    except RefreshError as exc:
        record_audit(
            db,
            action="auth.refresh.reuse_detected" if exc.reason == REASON_REUSED else "auth.refresh.failure",
            entity="user",
            request=request,
            details={"reason": exc.reason},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Сессия истекла, войдите заново",
        ) from exc

    record_audit(db, action="auth.refresh", actor_user_id=user.id, entity="user", entity_id=user.id, request=request)
    return TokenPairResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        user=_user_response(db, user),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(payload: RefreshPayload, request: Request, db: DbSession) -> Response:
    revoke_refresh_token(db, payload.refresh_token)
    record_audit(db, action="auth.logout", entity="user", request=request)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserResponse)
def me(user: CurrentUser, db: DbSession) -> UserResponse:
    return _user_response(db, user)


@router.get("/consents/required", response_model=list[ConsentRequirement])
def required_consents() -> list[ConsentRequirement]:
    """Актуальные версии согласий. Задаёт backend, чтобы фронтенд не дублировал юридические тексты."""
    return [ConsentRequirement(kind=kind, version=version) for kind, version in CONSENT_VERSIONS.items()]


@router.post("/consents", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def accept_consents(payload: ConsentsPayload, request: Request, user: CurrentUser, db: DbSession) -> UserResponse:
    pairs = _consent_pairs(payload)
    problems = validate_consents(pairs)
    if problems:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "invalid_consents", "problems": problems},
        )
    record_consents(db, user.id, pairs, client_ip(request))
    db.commit()
    record_audit(
        db,
        action="consent.accepted",
        actor_user_id=user.id,
        entity="user",
        entity_id=user.id,
        request=request,
        details={"kinds": [kind for kind, _ in pairs]},
    )
    return _user_response(db, user)
