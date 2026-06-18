from __future__ import annotations

import base64
import hashlib
import os
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Optional
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken
import jwt
import bcrypt
from jwt.exceptions import PyJWTError as JWTError
from sqlalchemy.orm import Session

from api.database import EmailVerificationCodeDB, UserDB, UserLLMConfigDB


ALGORITHM = "HS256"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


_DEFAULT_SECRET = "tradingagents-ashare-dev-secret"


def _secret_key() -> str:
    return os.getenv("TA_APP_SECRET_KEY") or _DEFAULT_SECRET


def _fernet_from_key(key: str) -> Fernet:
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _fernet() -> Fernet:
    return _fernet_from_key(_secret_key())


def is_custom_secret_configured() -> bool:
    return bool(os.getenv("TA_APP_SECRET_KEY"))


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    try:
        return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return None


def decrypt_secret_with_fallback(value: Optional[str]) -> Optional[str]:
    """Decrypt trying current key first, then default key as fallback."""
    if not value:
        return None
    # Try current key
    try:
        return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        pass
    # Try default key (first-time migration: no key → custom key)
    if is_custom_secret_configured():
        try:
            return _fernet_from_key(_DEFAULT_SECRET).decrypt(value.encode("utf-8")).decode("utf-8")
        except InvalidToken:
            pass
    return None


def normalize_email(email: str) -> str:
    return email.strip().lower()


def generate_login_code() -> str:
    return f"{secrets.randbelow(1000000):06d}"


def hash_code(email: str, code: str) -> str:
    return hashlib.sha256(f"{normalize_email(email)}:{code}:{_secret_key()}".encode("utf-8")).hexdigest()


def create_access_token(user: UserDB, expires_days: int = 30) -> str:
    now = _utcnow()
    payload = {
        "sub": user.id,
        "email": user.email,
        "exp": now + timedelta(days=expires_days),
        "iat": now,
    }
    return jwt.encode(payload, _secret_key(), algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, _secret_key(), algorithms=[ALGORITHM])


def get_user_by_email(db: Session, email: str) -> Optional[UserDB]:
    return db.query(UserDB).filter(UserDB.email == normalize_email(email)).first()


def get_user_by_id(db: Session, user_id: str) -> Optional[UserDB]:
    return db.query(UserDB).filter(UserDB.id == user_id).first()


def upsert_login_code(db: Session, email: str, purpose: str = "login") -> str:
    email = normalize_email(email)
    code = generate_login_code()
    now = _utcnow()

    db.query(EmailVerificationCodeDB).filter(
        EmailVerificationCodeDB.email == email,
        EmailVerificationCodeDB.purpose == purpose,
        EmailVerificationCodeDB.consumed_at.is_(None),
    ).update({"consumed_at": now})

    row = EmailVerificationCodeDB(
        id=str(uuid4()),
        email=email,
        code_hash=hash_code(email, code),
        purpose=purpose,
        expires_at=now + timedelta(minutes=10),
        created_at=now,
    )
    db.add(row)
    db.commit()
    return code


def verify_login_code(db: Session, email: str, code: str, purpose: str = "login", client_ip: Optional[str] = None) -> Optional[UserDB]:
    email = normalize_email(email)
    now = _utcnow()
    code_row = (
        db.query(EmailVerificationCodeDB)
        .filter(
            EmailVerificationCodeDB.email == email,
            EmailVerificationCodeDB.purpose == purpose,
            EmailVerificationCodeDB.consumed_at.is_(None),
        )
        .order_by(EmailVerificationCodeDB.created_at.desc())
        .first()
    )
    expires_at = _as_utc(code_row.expires_at) if code_row else None
    if not code_row or not expires_at or expires_at < now:
        return None
    if code_row.code_hash != hash_code(email, code):
        return None

    code_row.consumed_at = now
    user = get_user_by_email(db, email)
    if not user:
        user = UserDB(
            id=str(uuid4()),
            email=email,
            is_active=True,
            created_at=now,
            updated_at=now,
            last_login_at=now,
            last_login_ip=client_ip,
        )
        db.add(user)
    else:
        user.last_login_at = now
        user.last_login_ip = client_ip
        user.updated_at = now
    db.commit()
    db.refresh(user)
    return user


def get_env_alias(keys: list[str], default: str = "") -> str:
    for k in keys:
        v = os.getenv(k)
        if v is not None:
            return v
    return default


def send_login_code(email: str, code: str) -> Optional[str]:
    smtp_host = get_env_alias(["MAIL_HOST", "MAIL_SERVER", "SMTP_HOST"]).strip()
    if not smtp_host:
        print(f"[auth] login code for {email}: {code}")
        if os.getenv("APP_ENV", "development") != "production":
            return code
        return None

    smtp_port = int(get_env_alias(["MAIL_PORT", "SMTP_PORT"]) or "587")
    smtp_user = get_env_alias(["MAIL_USER", "MAIL_USERNAME", "SMTP_USER"]).strip()
    smtp_password = get_env_alias(["MAIL_PASS", "MAIL_PASSWORD", "SMTP_PASSWORD"]).strip()
    smtp_from = get_env_alias(["MAIL_FROM", "SMTP_FROM"], smtp_user or "noreply@example.com").strip()
    
    # 兼容旧版的逻辑
    smtp_starttls_str = get_env_alias(["MAIL_STARTTLS", "SMTP_TLS"], "1").strip().lower()
    smtp_starttls = smtp_starttls_str not in ("0", "false", "off", "no")
    
    smtp_ssl_tls_str = get_env_alias(["MAIL_SSL", "MAIL_SSL_TLS"], "0").strip().lower()
    smtp_ssl_tls = smtp_ssl_tls_str in ("1", "true", "on", "yes")

    msg = EmailMessage()
    msg["Subject"] = "TradingAgents 登录验证码"
    msg["From"] = smtp_from
    msg["To"] = email
    msg.set_content(f"你的 TradingAgents 登录验证码是：{code}\n\n10 分钟内有效。")

    try:
        print(f"[auth] connecting to {smtp_host}:{smtp_port} (SSL: {smtp_ssl_tls}, STARTTLS: {smtp_starttls})")
        smtp_cls = smtplib.SMTP_SSL if smtp_ssl_tls else smtplib.SMTP
        with smtp_cls(smtp_host, smtp_port, timeout=20) as server:
            if smtp_starttls and not smtp_ssl_tls:
                server.starttls()
            if smtp_user:
                server.login(smtp_user, smtp_password)
            server.send_message(msg)
        return None
    except Exception as e:
        print(f"[auth] failed to send email via {smtp_host}: {e}")
        print(f"[auth] falling back to console log. code for {email}: {code}")
        if os.getenv("APP_ENV", "development") != "production":
            return code
        return None


def get_user_llm_config(db: Session, user_id: str) -> Optional[UserLLMConfigDB]:
    return db.query(UserLLMConfigDB).filter(UserLLMConfigDB.user_id == user_id).first()


def upsert_user_llm_config(
    db: Session,
    user_id: str,
    *,
    llm_provider: Optional[str] = None,
    backend_url: Optional[str] = None,
    quick_think_llm: Optional[str] = None,
    deep_think_llm: Optional[str] = None,
    max_debate_rounds: Optional[int] = None,
    max_risk_discuss_rounds: Optional[int] = None,
    searxng_base_url: Optional[str] = None,
    news_data_strategy: Optional[str] = None,
    news_hybrid_min_items: Optional[int] = None,
    news_hybrid_min_confidence: Optional[float] = None,
    news_aggregate_max_items: Optional[int] = None,
    news_aggregate_max_chars: Optional[int] = None,
    news_dedupe_enabled: Optional[bool] = None,
    tushare_enabled: Optional[bool] = None,
    tushare_token: Optional[str] = None,
    tushare_proxy_url: Optional[str] = None,
    tushare_timeout: Optional[int] = None,
    tushare_rate_limit_per_minute: Optional[int] = None,
    tushare_cache_ttl_seconds: Optional[int] = None,
    tushare_capability_cache_ttl_seconds: Optional[int] = None,
    tushare_capabilities: Optional[dict] = None,
    tushare_last_checked_at: Optional[datetime] = None,
    api_key: Optional[str] = None,
    wecom_webhook_url: Optional[str] = None,
    clear_api_key: bool = False,
    clear_wecom_webhook: bool = False,
    clear_tushare_token: bool = False,
    default_analysts: Optional[list] = None,
) -> UserLLMConfigDB:
    row = get_user_llm_config(db, user_id)
    now = _utcnow()
    if not row:
        row = UserLLMConfigDB(user_id=user_id, created_at=now, updated_at=now)
        db.add(row)

    if llm_provider is not None:
        row.llm_provider = llm_provider
    if backend_url is not None:
        row.backend_url = backend_url
    if quick_think_llm is not None:
        row.quick_think_llm = quick_think_llm
    if deep_think_llm is not None:
        row.deep_think_llm = deep_think_llm
    if max_debate_rounds is not None:
        row.max_debate_rounds = max_debate_rounds
    if max_risk_discuss_rounds is not None:
        row.max_risk_discuss_rounds = max_risk_discuss_rounds
    if searxng_base_url is not None:
        row.searxng_base_url = searxng_base_url or None
    if news_data_strategy is not None:
        row.news_data_strategy = news_data_strategy
    if news_hybrid_min_items is not None:
        row.news_hybrid_min_items = int(news_hybrid_min_items)
    if news_hybrid_min_confidence is not None:
        row.news_hybrid_min_confidence = float(news_hybrid_min_confidence)
    if news_aggregate_max_items is not None:
        row.news_aggregate_max_items = int(news_aggregate_max_items)
    if news_aggregate_max_chars is not None:
        row.news_aggregate_max_chars = int(news_aggregate_max_chars)
    if news_dedupe_enabled is not None:
        row.news_dedupe_enabled = bool(news_dedupe_enabled)
    if tushare_enabled is not None:
        row.tushare_enabled = bool(tushare_enabled)
    if tushare_proxy_url is not None:
        row.tushare_proxy_url = tushare_proxy_url.strip() or None
    if tushare_timeout is not None:
        row.tushare_timeout = int(tushare_timeout)
    if tushare_rate_limit_per_minute is not None:
        row.tushare_rate_limit_per_minute = int(tushare_rate_limit_per_minute)
    if tushare_cache_ttl_seconds is not None:
        row.tushare_cache_ttl_seconds = int(tushare_cache_ttl_seconds)
    if tushare_capability_cache_ttl_seconds is not None:
        row.tushare_capability_cache_ttl_seconds = int(tushare_capability_cache_ttl_seconds)
    if tushare_capabilities is not None:
        row.tushare_capabilities = tushare_capabilities
    if tushare_last_checked_at is not None:
        row.tushare_last_checked_at = tushare_last_checked_at

    if clear_api_key:
        row.api_key = None
        row.api_key_encrypted = None
    elif api_key:
        row.api_key = api_key

    if clear_tushare_token:
        row.tushare_token = None
        row.tushare_token_encrypted = None
    elif tushare_token:
        row.tushare_token = tushare_token

    if clear_wecom_webhook:
        row.wecom_webhook_encrypted = None
    elif wecom_webhook_url:
        row.wecom_webhook_encrypted = encrypt_secret(wecom_webhook_url)

    if default_analysts is not None:
        import json
        row.default_analysts = json.dumps(default_analysts)

    row.updated_at = now
    db.commit()
    db.refresh(row)
    return row


# ─── Password Authentication ────────────────────────────────────────────────

MIN_PASSWORD_LENGTH = 6


def hash_password(password: str) -> str:
    """Hash a password with bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its bcrypt hash."""
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def validate_password_strength(password: str) -> None:
    """Raise ValueError if password does not meet strength requirements."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"密码长度不能少于 {MIN_PASSWORD_LENGTH} 位")


def register_with_password(
    db: Session,
    email: str,
    password: str,
    client_ip: Optional[str] = None,
) -> UserDB:
    """Register a new user with email + password. Returns the new user."""
    email = normalize_email(email)
    existing = get_user_by_email(db, email)
    if existing:
        # If this user already has a password, reject
        if existing.password_hash:
            raise ValueError("该邮箱已注册，请直接登录")
        # Existing user without password (email-code only) — set password
        existing.password_hash = hash_password(password)
        existing.updated_at = _utcnow()
        db.commit()
        db.refresh(existing)
        return existing

    validate_password_strength(password)
    now = _utcnow()
    user = UserDB(
        id=str(uuid4()),
        email=email,
        password_hash=hash_password(password),
        is_active=True,
        created_at=now,
        updated_at=now,
        last_login_at=now,
        last_login_ip=client_ip,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def login_with_password(
    db: Session,
    email: str,
    password: str,
    client_ip: Optional[str] = None,
) -> Optional[UserDB]:
    """Login with email + password. Returns user on success, None on failure."""
    email = normalize_email(email)
    user = get_user_by_email(db, email)
    if not user or not user.password_hash:
        return None
    if not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    now = _utcnow()
    user.last_login_at = now
    user.last_login_ip = client_ip
    user.updated_at = now
    db.commit()
    db.refresh(user)
    return user


def change_password(
    db: Session,
    user_id: str,
    old_password: str,
    new_password: str,
) -> None:
    """Change password for an existing user. Raises ValueError on failure."""
    user = get_user_by_id(db, user_id)
    if not user or not user.password_hash:
        raise ValueError("用户不存在或未设置密码")
    if not verify_password(old_password, user.password_hash):
        raise ValueError("当前密码不正确")
    validate_password_strength(new_password)
    user.password_hash = hash_password(new_password)
    user.updated_at = _utcnow()
    db.commit()
