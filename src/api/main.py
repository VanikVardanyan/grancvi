from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.errors import register_exception_handlers
from src.api.routes import admin as admin_routes
from src.api.routes import bookings as bookings_routes
from src.api.routes import master as master_routes
from src.api.routes import masters as masters_routes
from src.api.routes import me as me_routes
from src.config import settings

app = FastAPI(title="grancvi api", version="0.1.0", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.api_cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["X-Telegram-Init-Data", "Content-Type"],
    max_age=600,
)

register_exception_handlers(app)
app.include_router(me_routes.router)
app.include_router(masters_routes.router)
app.include_router(master_routes.router)
app.include_router(bookings_routes.router)
app.include_router(admin_routes.router)


@app.get("/v1/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
