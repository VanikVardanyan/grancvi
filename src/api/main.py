from __future__ import annotations

from fastapi import FastAPI

from src.api.errors import register_exception_handlers
from src.api.routes import bookings as bookings_routes
from src.api.routes import masters as masters_routes

app = FastAPI(title="grancvi api", version="0.1.0", docs_url=None, redoc_url=None)
register_exception_handlers(app)
app.include_router(masters_routes.router)
app.include_router(bookings_routes.router)


@app.get("/v1/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
