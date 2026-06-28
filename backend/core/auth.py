from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta
from typing import Any
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.config import Settings, get_settings
from backend.core.database import get_db
from backend.core.models import AppUser


def admin_emails(settings: Settings | None = None) -> set[str]:
    current = settings or get_settings()
    return {
        email.strip().lower()
        for email in current.admin_emails.split(",")
        if email.strip()
    }


def ensure_admin_user(db: Session) -> None:
    settings = get_settings()
    for email in admin_emails(settings):
        user = db.scalar(select(AppUser).where(AppUser.email == email))
        if user:
            user.role = "admin"
            user.status = "approved"
            user.updated_at = datetime.utcnow()
            continue
        db.add(
            AppUser(
                google_sub=f"admin:{email}",
                email=email,
                name=email.split("@")[0],
                role="admin",
                status="approved",
            )
        )
    db.commit()


def verify_google_credential(credential: str) -> dict[str, str]:
    settings = get_settings()
    if not settings.google_client_id and settings.allow_dev_mocks:
        return _decode_dev_credential(credential)
    if not settings.google_client_id:
        raise HTTPException(status_code=503, detail="GOOGLE_CLIENT_ID is not configured.")
    try:
        from google.oauth2 import id_token
        from google.auth.transport import requests

        payload = id_token.verify_oauth2_token(
            credential,
            requests.Request(),
            settings.google_client_id,
        )
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Google sign-in failed: {exc}") from exc
    return _identity_from_payload(payload)


def create_or_update_user(db: Session, identity: dict[str, str]) -> AppUser:
    email = identity["email"].lower()
    user = db.scalar(select(AppUser).where(AppUser.email == email))
    role = "admin" if email in admin_emails() else "user"
    status_value = "approved" if role == "admin" else "pending"
    if user:
        user.google_sub = identity["sub"]
        user.name = identity.get("name") or user.name
        user.picture = identity.get("picture") or user.picture
        user.role = role
        if role == "admin":
            user.status = "approved"
        elif user.status not in {"approved", "disabled", "deleted"}:
            user.status = "pending"
        user.updated_at = datetime.utcnow()
    else:
        user = AppUser(
            google_sub=identity["sub"],
            email=email,
            name=identity.get("name") or email,
            picture=identity.get("picture"),
            role=role,
            status=status_value,
        )
        db.add(user)
    db.commit()
    db.refresh(user)
    return user


def create_access_token(user: AppUser) -> str:
    settings = get_settings()
    expires_at = int(
        (datetime.utcnow() + timedelta(minutes=settings.auth_token_expire_minutes)).timestamp()
    )
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role,
        "exp": expires_at,
    }
    body = _b64(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = _sign(body, settings.app_jwt_secret)
    return f"{body}.{signature}"


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> AppUser:
    auth_header = request.headers.get("Authorization", "")
    scheme, _, token = auth_header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    payload = _decode_access_token(token)
    user = db.get(AppUser, int(payload["sub"]))
    if not user or user.status != "approved":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is not approved.")
    return user


def get_current_admin(user: AppUser = Depends(get_current_user)) -> AppUser:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required.")
    return user


def _decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    body, sep, signature = token.partition(".")
    if not sep or not hmac.compare_digest(signature, _sign(body, settings.app_jwt_secret)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid auth token.")
    try:
        payload = json.loads(_unb64(body).decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid auth token.") from exc
    if int(payload.get("exp") or 0) < int(datetime.utcnow().timestamp()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Auth token expired.")
    return payload


def _decode_dev_credential(credential: str) -> dict[str, str]:
    try:
        payload = json.loads(credential)
    except json.JSONDecodeError:
        payload = _decode_unsigned_jwt_payload(credential)
    return _identity_from_payload(payload)


def _decode_unsigned_jwt_payload(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) < 2:
        raise HTTPException(status_code=401, detail="Invalid development Google credential.")
    try:
        return json.loads(_unb64(parts[1]).decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid development Google credential.") from exc


def _identity_from_payload(payload: dict[str, Any]) -> dict[str, str]:
    email = str(payload.get("email") or "").lower()
    sub = str(payload.get("sub") or "")
    if not email or "@" not in email or not sub:
        raise HTTPException(status_code=401, detail="Google credential is missing email or subject.")
    return {
        "sub": sub,
        "email": email,
        "name": str(payload.get("name") or email),
        "picture": str(payload.get("picture") or ""),
    }


def _sign(body: str, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
    return _b64(digest)


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)
