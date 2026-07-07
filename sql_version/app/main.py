"""FastAPI entry point for the SQLite version.

A ``lifespan`` handler creates the tables and seeds the example data once, at
startup. Doing it here (instead of at import time) keeps merely importing this
module free of side effects — tests can import ``app`` without touching the real
database file. The rest is the same centralized error handling and frontend
mount as the in-memory version.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .db import connect, init_db
from .errors import AppError
from .routes import router
from .seed import seed_if_empty

# frontend/ lives two levels up: sql_version/app/main.py -> sec-task-2/frontend
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables and seed once, before the app starts serving requests.
    conn = connect()
    try:
        init_db(conn)
        seed_if_empty(conn)
    finally:
        conn.close()
    yield


app = FastAPI(title="RBAC Service (SQLite)", version="2.0.0-sql", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def disable_caching(request: Request, call_next):
    # Dev/demo convenience: never serve stale frontend assets from cache.
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(AppError)
def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


@app.exception_handler(RequestValidationError)
def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": "Request validation failed",
                "details": jsonable_encoder(exc.errors()),
            }
        },
    )


# API routes first, then the static frontend at the root.
app.include_router(router)
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
