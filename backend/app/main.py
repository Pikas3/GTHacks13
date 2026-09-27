"""FastAPI application factory for AskLepius (hackathon prototype)."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.api.router import api_router
from app.config import Settings, get_settings
from app.db.session import detect_capabilities
from app.dependencies import ServiceContainer
from app.errors import AppError, ErrorBody, ErrorCode, ErrorResponse
from app.observability import RequestContextMiddleware, configure_logging, request_id_var

logger = logging.getLogger("lepius")


def _error(code: ErrorCode, message: str, status: int, details: dict | None = None) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorBody(code=code, message=message, details=details or {}, request_id=request_id_var.get())
    )
    return JSONResponse(status_code=status, content=body.model_dump(mode="json"))


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        container = ServiceContainer.create(settings)
        try:
            container.capabilities = await detect_capabilities(container.engine)
        except Exception as exc:
            logger.warning("database not reachable at startup", extra={"error": type(exc).__name__})
        logger.info(
            "startup",
            extra={
                "ai_mode": container.ai.mode,
                "stt": container.stt.name,
                "tts": container.tts.name,
                "capabilities": container.capabilities,
            },
        )
        app.state.container = container
        yield
        await container.aclose()

    app = FastAPI(
        title="AskLepius API",
        version="0.1.0",
        description="Hackathon prototype. Synthetic HCPs and fictional products only.",
        lifespan=lifespan,
    )
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["x-request-id", "x-tts-provider", "x-tts-placeholder"],
    )

    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return _error(exc.code, exc.message, exc.status_code, exc.details)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return _error(ErrorCode.VALIDATION_ERROR, "Invalid request", 422, {"errors": exc.errors()})

    @app.exception_handler(SQLAlchemyError)
    async def db_error_handler(_: Request, exc: SQLAlchemyError) -> JSONResponse:
        logger.exception("database error")
        return _error(
            ErrorCode.DATABASE_UNAVAILABLE,
            "Database unavailable or not migrated. Run `make db-up migrate seed`.",
            503,
        )

    @app.exception_handler(OSError)
    async def connection_error_handler(_: Request, exc: OSError) -> JSONResponse:
        logger.warning("connection error", extra={"error": type(exc).__name__})
        return _error(ErrorCode.DATABASE_UNAVAILABLE, "Database connection failed", 503)

    @app.exception_handler(Exception)
    async def unhandled_handler(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error")
        return _error(ErrorCode.INTERNAL_ERROR, "Unexpected server error", 500)

    app.include_router(api_router)
    return app


app = create_app()
