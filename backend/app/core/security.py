import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models import Role, User

COOKIE_NAME = "casesync_session"
CSRF_COOKIE = "casesync_csrf"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


def create_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": user.id, "role": user.role.value, "iat": now, "exp": now + timedelta(minutes=settings.access_token_minutes)}
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session is invalid or expired") from exc


def new_csrf() -> str:
    return secrets.token_urlsafe(32)


def csrf_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def get_current_user(
    token: str | None = Cookie(default=None, alias=COOKIE_NAME),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not token and authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1]
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    payload = decode_token(token)
    user = db.get(User, payload["sub"])
    if not user or not user.active:
        raise HTTPException(status_code=401, detail="Account is unavailable")
    return user


def verify_csrf(request: Request, csrf_cookie: str | None = Cookie(default=None, alias=CSRF_COOKIE), csrf_header: str | None = Header(default=None, alias="X-CSRF-Token")):
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        if not csrf_cookie or not csrf_header or not hmac.compare_digest(csrf_cookie, csrf_header):
            raise HTTPException(status_code=403, detail="CSRF validation failed")


def require_roles(*roles: Role):
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return dependency


def can_view_all(user: User) -> bool:
    return user.role in {Role.SYSTEM_ADMIN, Role.CENTRAL_ADMIN, Role.AUDITOR}


def can_mutate_case(user: User, complaint) -> bool:
    if user.role in {Role.SYSTEM_ADMIN, Role.CENTRAL_ADMIN}:
        return True
    if user.role == Role.BUREAU_HEAD:
        return user.bureau_id == complaint.assigned_bureau_id
    return user.role == Role.CASE_OFFICER and user.id == complaint.assigned_officer_id


