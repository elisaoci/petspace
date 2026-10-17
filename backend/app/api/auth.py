"""Авторизация владельца: регистрация и вход по паролю, вход по коду на email, согласия."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession
from app.config import Settings, get_settings
from app.models import (
    CONSENT_VERSIONS,
    REQUIRED_CONSENTS,
    ROLE_OWNER,
    STATUS_ACTIVE,
    OtpCode,
    User,
)
from app.schemas.auth import (
    ConsentRequirement,
    ConsentsPayload,
    LoginPayload,
    OtpRequestPayload,
    OtpRequestResponse,
    OtpVerifyPayload,
    RefreshPayload,
    RegisterPayload,
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
from app.services.passwords import hash_password, verify_password
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

INVALID_CREDENTIALS = "Неверный email или пароль"


def _user_response(db: Session, user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        phone=user.phone,
        role=user.role,
        status=user.status,
        consents_accepted=not missing_required_consents(db, user.id),
        has_password=user.password_hash is not None,
        created_at=user.created_at,
    )


def _consent_pairs(payload: ConsentsPayload) -> list[tuple[str, str]]:
    return [(item.kind, item.version) for item in payload.consents]


def _missing_required(pairs: list[tuple[str, str]]) -> list[str]:
    provided = {kind for kind, _ in pairs}
    return [kind for kind in REQUIRED_CONSENTS if kind not in provided]


def _invalidate_consents(problems: list[str]) -> None:
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"error": "invalid_consents", "problems": problems},
    )


def _complete_login(
    db: Session, user: User, request: Request, settings: Settings, *, action: str
) -> TokenPairResponse:
    """Выдаёт пару токенов и пишет событие входа в аудит."""
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
        action=action,
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


@router.post("/register", response_model=TokenPairResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterPayload, request: Request, db: DbSession) -> TokenPairResponse:
    """Регистрация владельца: email, пароль и обязательные согласия."""
    settings = get_settings()
    pairs = [(item.kind, item.version) for item in payload.consents]

    problems = validate_consents(pairs)
    if problems:
        _invalidate_consents(problems)
    missing = _missing_required(pairs)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "consent_required", "kinds": missing, "message": "Примите все согласия"},
        )

    if db.scalar(select(User).where(User.email == payload.email)) is not None:
        record_audit(
            db,
            action="auth.register.rejected",
            entity="user",
            request=request,
            details={"email": payload.email, "reason": "email_taken"},
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "email_taken", "message": "Этот email уже зарегистрирован — войдите"},
        )

    now = datetime.now(UTC)
    user = User(
        email=payload.email,
        role=ROLE_OWNER,
        status=STATUS_ACTIVE,
        password_hash=hash_password(payload.password, settings.password_iterations),
        email_verified_at=now,
        last_login_at=now,
    )
    db.add(user)
    db.flush()
    record_consents(db, user.id, pairs, client_ip(request))

    return _complete_login(db, user, request, settings, action="user.registered")


@router.post("/login", response_model=TokenPairResponse)
def login(payload: LoginPayload, request: Request, db: DbSession) -> TokenPairResponse:
    """Вход по паролю. Ответ на неверные данные одинаковый: не подсказываем,
    существует ли такой email."""
    settings = get_settings()
    now = datetime.now(UTC)
    user = db.scalar(select(User).where(User.email == payload.email))

    if user is None:
        record_audit(
            db,
            action="auth.login.failure",
            entity="user",
            request=request,
            details={"email": payload.email, "reason": "unknown_email"},
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=INVALID_CREDENTIALS)

    if user.status != STATUS_ACTIVE:
        record_audit(
            db,
            action="auth.login.failure",
            actor_user_id=user.id,
            entity="user",
            entity_id=user.id,
            request=request,
            details={"reason": "blocked"},
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=INVALID_CREDENTIALS)

    if user.locked_until is not None and user.locked_until > now:
        retry_after = max(int((user.locked_until - now).total_seconds()), 1)
        record_audit(
            db,
            action="auth.login.failure",
            actor_user_id=user.id,
            entity="user",
            entity_id=user.id,
            request=request,
            details={"reason": "locked"},
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Слишком много неудачных попыток. Попробуйте позже или войдите по коду с почты.",
            headers={"Retry-After": str(retry_after)},
        )

    if user.password_hash is None:
        record_audit(
            db,
            action="auth.login.failure",
            actor_user_id=user.id,
            entity="user",
            entity_id=user.id,
            request=request,
            details={"reason": "password_not_set"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "password_not_set", "message": "У аккаунта нет пароля — войдите по коду с почты"},
        )

    if not verify_password(payload.password, user.password_hash):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= settings.login_max_attempts:
            user.locked_until = now + timedelta(minutes=settings.login_lockout_minutes)
            user.failed_login_attempts = 0
        db.commit()
        record_audit(
            db,
            action="auth.login.failure",
            actor_user_id=user.id,
            entity="user",
            entity_id=user.id,
            request=request,
            details={"reason": "wrong_password", "attempts": user.failed_login_attempts},
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=INVALID_CREDENTIALS)

    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = now
    return _complete_login(db, user, request, settings, action="auth.login")


@router.post("/otp/request", response_model=OtpRequestResponse, status_code=status.HTTP_202_ACCEPTED)
def request_otp(payload: OtpRequestPayload, request: Request, db: DbSession) -> OtpRequestResponse:
    """Отправляет код входа. Ответ одинаковый для существующих и неизвестных адресов:
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
        # Код отдаётся только при явно включённом EXPOSE_DEV_OTP (локальная разработка).
        dev_code=code if settings.expose_dev_otp else None,
    )


@router.post("/otp/verify", response_model=TokenPairResponse)
def verify_otp(payload: OtpVerifyPayload, request: Request, db: DbSession) -> TokenPairResponse:
    """Вход по коду — альтернатива паролю для существующего аккаунта.

    Регистрации здесь нет: аккаунт создаётся только через `/auth/register`,
    где принимаются согласия.
    """
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
    if user is None:
        record_audit(
            db,
            action="otp.verify.failure",
            entity="otp",
            request=request,
            details={"destination": destination, "reason": "unknown_email"},
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "user_not_found", "message": "Аккаунт не найден — зарегистрируйтесь"},
        )
    if user.status != STATUS_ACTIVE:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=INVALID_CREDENTIALS)

    otp.consumed_at = now
    user.email_verified_at = user.email_verified_at or now
    user.last_login_at = now
    return _complete_login(db, user, request, settings, action="auth.login.code")


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
        _invalidate_consents(problems)
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
