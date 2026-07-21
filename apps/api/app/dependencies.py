from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import Settings, get_settings
from .database import get_db
from .models import User
from .security import AuthenticationError, decode_session

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


def require_origin(request: Request, settings: Config) -> None:
    origin = request.headers.get("origin")
    if settings.app_env == "test":
        return
    if origin != settings.public_origin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "origin rejected")
