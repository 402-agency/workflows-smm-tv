"""Shared FastAPI dependencies (DB session + auth)."""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.database import get_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

_basic = HTTPBasic(auto_error=False)


def _token_ok(request: Request, settings: Settings) -> bool:
    if not settings.api_token:
        return False
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        candidate = header[7:].strip()
        if secrets.compare_digest(candidate, settings.api_token):
            return True
    query_token = request.query_params.get("token")
    return bool(query_token and secrets.compare_digest(query_token, settings.api_token))


def _basic_ok(credentials: HTTPBasicCredentials | None, settings: Settings) -> bool:
    if credentials is None:
        return False
    user_ok = secrets.compare_digest(credentials.username, settings.auth_username)
    pass_ok = secrets.compare_digest(credentials.password, settings.auth_password)
    return user_ok and pass_ok


def require_auth(
    request: Request,
    settings: SettingsDep,
    credentials: Annotated[HTTPBasicCredentials | None, Depends(_basic)] = None,
) -> None:
    """Guard write endpoints. Accepts HTTP Basic or a bearer/query API token."""
    if _token_ok(request, settings) or _basic_ok(credentials, settings):
        return
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Basic"},
    )


AuthDep = Depends(require_auth)
