from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import redis.asyncio as redis
import structlog
from aiogram import Bot
from aiogram.types import Update
from fastapi import FastAPI, Header, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from .bot import configure_bot, create_dispatcher
from .config import get_settings
from .database import Base, create_database
from .nonce_store import RedisChallengeStore
from .routes import router
from .ton import TonClient

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    engine, session_factory = create_database(settings)
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.redis = redis.from_url(settings.redis_url, decode_responses=True)
    app.state.challenge_store = RedisChallengeStore(app.state.redis)
    app.state.http = httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=3.0))
    app.state.ton_client = TonClient(app.state.http, settings)
    app.state.bot = None
    app.state.dispatcher = None
    if settings.auto_create_schema:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    if settings.bot_token.get_secret_value():
        app.state.bot = Bot(settings.bot_token.get_secret_value())
        app.state.dispatcher = create_dispatcher(settings, session_factory)
        if settings.app_env == "production":
            await configure_bot(app.state.bot, settings)
    yield
    if app.state.bot:
        await app.state.bot.session.close()
    await app.state.http.aclose()
    await app.state.redis.aclose()
    await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="LOOP API",
        version="0.1.0",
        docs_url=None if settings.app_env == "production" else "/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        max_age=600,
    )
    app.include_router(router)

    @app.get("/live", include_in_schema=False)
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready", include_in_schema=False)
    async def ready(request: Request) -> dict[str, str]:
        try:
            async with request.app.state.engine.connect() as connection:
                await connection.exec_driver_sql("SELECT 1")
            await request.app.state.redis.ping()
        except Exception as exc:
            logger.warning("readiness_failed", error=type(exc).__name__)
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "dependencies unavailable"
            ) from exc
        return {"status": "ready"}

    @app.get("/metrics", include_in_schema=False)
    async def metrics(authorization: str | None = Header(default=None)) -> Response:
        token = settings.metrics_token.get_secret_value()
        if token and authorization != f"Bearer {token}":
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required")
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.post(settings.webhook_path, include_in_schema=False)
    async def telegram_webhook(
        request: Request,
        secret: str | None = Header(default=None, alias="X-Telegram-Bot-Api-Secret-Token"),
    ) -> dict[str, bool]:
        expected = settings.telegram_webhook_secret.get_secret_value()
        if not expected or secret != expected:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "webhook secret rejected")
        if request.app.state.bot is None or request.app.state.dispatcher is None:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "bot unavailable")
        update = Update.model_validate(await request.json(), context={"bot": request.app.state.bot})
        await request.app.state.dispatcher.feed_update(request.app.state.bot, update)
        return {"ok": True}

    return app


app = create_app()
