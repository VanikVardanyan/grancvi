from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="grancvi api", version="0.1.0", docs_url=None, redoc_url=None)


@app.get("/v1/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
