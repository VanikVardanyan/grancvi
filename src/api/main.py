from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis as _Redis

from src.api.errors import register_exception_handlers
from src.api.routes import admin as admin_routes
from src.api.routes import bookings as bookings_routes
from src.api.routes import master as master_routes
from src.api.routes import masters as masters_routes
from src.api.routes import me as me_routes
from src.api.routes import public as public_routes
from src.api.routes import register as register_routes
from src.api.routes import salon as salon_routes
from src.api.routes import salons as salons_routes
from src.api.routes import search as search_routes
from src.api.routes import specialties as specialties_routes
from src.config import settings


def _init_sentry() -> None:
    """Turn on Sentry error reporting if SENTRY_DSN is set in env.

    Uses the FastAPI integration so unhandled 5xx in route handlers get
    reported automatically. Performance tracing stays off — we're just
    looking for crashes, not latency histograms.
    """
    if not settings.sentry_dsn:
        return
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        traces_sample_rate=0.0,
        integrations=[FastApiIntegration(), SqlalchemyIntegration()],
        send_default_pii=False,
    )


_init_sentry()

app = FastAPI(title="grancvi api", version="0.1.0", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.api_cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["X-Telegram-Init-Data", "Content-Type"],
    max_age=600,
)

register_exception_handlers(app)
app.include_router(me_routes.router)
app.include_router(masters_routes.router)
app.include_router(master_routes.router)
app.include_router(bookings_routes.router)
app.include_router(admin_routes.router)
app.include_router(salon_routes.router)
app.include_router(salons_routes.router)
app.include_router(search_routes.router)
app.include_router(register_routes.router)
app.include_router(specialties_routes.router)
app.include_router(public_routes.router)


@app.on_event("startup")
async def _open_public_redis() -> None:
    app.state.redis = _Redis.from_url(settings.redis_url, decode_responses=False)


@app.on_event("shutdown")
async def _close_public_redis() -> None:
    redis = getattr(app.state, "redis", None)
    if redis is not None:
        await redis.aclose()


@app.get("/v1/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
