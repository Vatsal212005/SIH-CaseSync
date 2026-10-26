import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.core.config import settings
from app.jobs.scheduler import sla_scheduler

logging.basicConfig(level=logging.INFO, format="%(message)s")
structlog.configure(processors=[structlog.processors.TimeStamper(fmt="iso"), structlog.processors.JSONRenderer()])
log = structlog.get_logger()

@asynccontextmanager
async def lifespan(app: FastAPI):
    stop = asyncio.Event()
    task = asyncio.create_task(sla_scheduler(stop))
    yield
    stop.set()
    await task


app = FastAPI(title="AICTE CaseSync API", version="1.0.0", description="Secure complaint monitoring, overlap intelligence and cross-bureau coordination API. Demo data is synthetic.", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_list, allow_credentials=True, allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["Content-Type", "Authorization", "X-CSRF-Token"])


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        log.exception("unhandled_error", request_id=request_id, path=request.url.path)
        return JSONResponse({"detail": "An unexpected server error occurred", "request_id": request_id}, status_code=500)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    log.info("request", request_id=request_id, method=request.method, path=request.url.path, status=response.status_code, duration_ms=round((time.perf_counter()-started)*1000, 1))
    return response


app.include_router(router, prefix="/api/v1")


