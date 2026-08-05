import json

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from .dependencies import Db
from .models import NotificationOutbox, User
from .public_feed import KIND_PUBLIC_FEED, public_feed_facts, render_public_feed_card

router = APIRouter(prefix="/api/v1/public-feed", tags=["public-feed"])


@router.get("/cards/{outbox_id}.jpg", include_in_schema=False)
async def public_feed_image(outbox_id: str, db: Db) -> Response:
    if len(outbox_id) != 36 or not all(
        character.isalnum() or character == "-" for character in outbox_id
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "card not found")
    item = await db.scalar(
        select(NotificationOutbox).where(
            NotificationOutbox.id == outbox_id,
            NotificationOutbox.kind == KIND_PUBLIC_FEED,
        )
    )
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "card not found")
    user = await db.get(User, item.user_id)
    try:
        facts = public_feed_facts(item, user)
        content = await run_in_threadpool(render_public_feed_card, facts)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "card not found") from exc
    return Response(
        content=content,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )
