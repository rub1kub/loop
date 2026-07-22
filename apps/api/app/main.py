import asyncio
import hashlib
import secrets
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import httpx
import redis.asyncio as redis
import structlog
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import Update
from fastapi import FastAPI, Header, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from redis.exceptions import RedisError
from starlette.responses import JSONResponse

from .bot import configure_bot, create_dispatcher
from .config import get_settings
from .database import Base, create_database
from .metrics import DUEL_CANARY_REDIS_KEY, refresh_duel_metrics
from .modules.bank.router import router as bank_router
from .modules.duel.router import router as duel_router
from .nonce_store import RedisChallengeStore
from .routes import router
from .schemas import DuelCanaryReport
from .ton import TonClient, TonProviderError, normalize_address

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
    app.state.plush_ton_client = TonClient(
        app.state.http,
        settings,
        base_url=settings.plush_brick_toncenter_url,
    )
    if settings.app_env == "production":
        contracts = {
            "BANK": (settings.bank_contract_address, settings.bank_contract_code_hash),
            "DUEL": (
                settings.effective_duel_contract_address,
                settings.effective_duel_contract_code_hash,
            ),
        }
        for name, (address, expected) in contracts.items():
            actual_code_hash = ""
            for attempt in range(3):
                try:
                    actual_code_hash = await app.state.ton_client.get_contract_code_hash(address)
                    break
                except TonProviderError:
                    if attempt == 2:
                        raise
                    await asyncio.sleep(2**attempt)
            if not secrets.compare_digest(actual_code_hash, expected.removeprefix("0x").upper()):
                raise RuntimeError(f"configured {name} contract code hash mismatch")
    app.state.bot = None
    app.state.dispatcher = None
    if settings.auto_create_schema:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    if settings.bot_token.get_secret_value():
        app.state.bot = Bot(settings.bot_token.get_secret_value())
        app.state.dispatcher = create_dispatcher(settings, session_factory)
        if settings.app_env == "production":
            try:
                await asyncio.wait_for(configure_bot(app.state.bot, settings), timeout=20)
            except (TimeoutError, TelegramAPIError) as exc:
                # Bot profile synchronization is operational metadata. A
                # Telegram flood-wait must not take the authenticated API,
                # contract recovery paths or chain projections offline.
                logger.warning("bot_configuration_deferred", error=type(exc).__name__)
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
    app.include_router(bank_router, prefix="/api/v1")
    app.include_router(duel_router, prefix="/api/v1")

    @app.middleware("http")
    async def protect_api(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        is_mutation = request.method in {"POST", "PUT", "PATCH", "DELETE"}
        if not is_mutation or not request.url.path.startswith("/api/v1"):
            return await call_next(request)
        if settings.app_env != "test" and request.headers.get("origin") != settings.public_origin:
            return JSONResponse({"detail": "origin rejected"}, status_code=403)
        if settings.app_env != "production":
            return await call_next(request)

        authorization = request.headers.get("authorization", "")
        source = (
            hashlib.sha256(authorization.encode()).hexdigest()[:24]
            if authorization.startswith("Bearer ")
            else request.headers.get("x-real-ip")
            or (request.client.host if request.client else "unknown")
        )
        group = "auth" if request.url.path.endswith("/auth/telegram") else "api"
        limit = 20 if group == "auth" else 120
        bucket = int(time.time() // 60)
        key = f"loop:rate:{group}:{source}:{bucket}"
        try:
            async with request.app.state.redis.pipeline(transaction=True) as pipeline:
                pipeline.incr(key)
                pipeline.expire(key, 90)
                current, _ = await pipeline.execute()
        except RedisError as exc:
            logger.error("rate_limit_unavailable", error=type(exc).__name__)
            return JSONResponse({"detail": "service temporarily unavailable"}, status_code=503)
        if int(current) > limit:
            return JSONResponse(
                {"detail": "rate limit exceeded"},
                status_code=429,
                headers={"Retry-After": "60"},
            )
        return await call_next(request)

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
    async def metrics(
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> Response:
        token = settings.metrics_token.get_secret_value()
        if token and authorization != f"Bearer {token}":
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required")
        await refresh_duel_metrics(request.app.state.session_factory, request.app.state.redis)
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.post("/internal/duel-canary", include_in_schema=False)
    async def report_duel_canary(
        body: DuelCanaryReport,
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> dict[str, str | int]:
        token = settings.metrics_token.get_secret_value()
        if not token or authorization != f"Bearer {token}":
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required")
        try:
            configured_contract = normalize_address(settings.effective_duel_contract_address)
            supplied_contract = normalize_address(body.contract_address)
        except TonProviderError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        if body.network != settings.ton_network_id or supplied_contract != configured_contract:
            raise HTTPException(status.HTTP_409_CONFLICT, "canary context does not match DUEL")
        try:
            proof = await request.app.state.ton_client.verify_duel_settlement(
                body.settlement_tx_hash,
                settings.effective_duel_contract_address,
                body.duel_id,
            )
        except TonProviderError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
        timestamp = str(int(proof.confirmed_at.timestamp()))
        async with request.app.state.redis.pipeline(transaction=True) as pipeline:
            pipeline.set(DUEL_CANARY_REDIS_KEY, timestamp)
            pipeline.hset(
                "loop:duel:canary:last_proof",
                mapping={
                    "network": body.network,
                    "contract": configured_contract,
                    "duel_id": body.duel_id,
                    "settlement_tx_hash": proof.transaction_hash,
                    "confirmed_at": timestamp,
                },
            )
            await pipeline.execute()
        return {"status": "verified", "duel_id": body.duel_id, "confirmed_at": timestamp}

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
