import secrets
from typing import Annotated, cast

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import Settings, get_settings
from .database import get_db
from .models import User
from .security import (
    AuthenticationError,
    canonical_raw_address,
    decode_control_session,
    decode_session,
)
from .ton import TonProviderError, normalize_address

Db = Annotated[AsyncSession, Depends(get_db)]
Config = Annotated[Settings, Depends(get_settings)]


async def current_user(
    db: Db,
    settings: Config,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required")
    try:
        claims = decode_session(authorization[7:], settings)
    except AuthenticationError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    user = await db.scalar(select(User).where(User.id == claims["sub"]))
    if user is None or user.telegram_id != claims.get("tg"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "session user not found")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


async def current_control_wallet(request: Request, settings: Config) -> str:
    token = request.cookies.get("loop_control")
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "control authentication required")
    try:
        claims = decode_control_session(token, settings)
        configured = canonical_raw_address(normalize_address(settings.control_admin_wallet))
    except (AuthenticationError, TonProviderError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    if not secrets.compare_digest(claims["sub"].lower(), configured.lower()):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "control wallet is not authorized")
    return cast(str, claims["sub"])


ControlWallet = Annotated[str, Depends(current_control_wallet)]


def require_origin(request: Request, settings: Config) -> None:
    origin = request.headers.get("origin")
    if settings.app_env == "test":
        return
    if origin != settings.public_origin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "origin rejected")
