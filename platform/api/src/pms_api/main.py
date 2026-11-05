import asyncio
import hmac
import json
import logging
import time
from contextlib import asynccontextmanager, suppress
from uuid import uuid4

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from sqlalchemy.exc import DBAPIError
from starlette.exceptions import HTTPException

from pms_api import __version__
from pms_api.core.common import AppError
from pms_api.core.config import Settings, get_settings
from pms_api.database.session import check_schema, engine_for, sessions_for
from pms_api.security.identity import OIDCVerifier

REQUESTS = Counter("pms_http_requests_total", "HTTP requests", ["method", "route", "status"])
LATENCY = Histogram("pms_http_request_seconds", "HTTP duration", ["method", "route"])
logger = logging.getLogger("pms_api")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app):
        engine = engine_for(settings)
        from pms_api.integrations.llm import LLMClient
        from pms_api.integrations.storage import storage_for

        app.state.llm = LLMClient(
            settings.llm_timeout_seconds,
            health_timeout=settings.health_timeout_seconds,
            health_attempts=settings.health_attempts,
        )
        app.state.storage = storage_for(settings)
        app.state.engine = engine
        app.state.sessions = sessions_for(engine)
        app.state.speech_tasks = set()
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
            app.state.http = client
            app.state.oidc = OIDCVerifier(settings, client)
            from pms_api.modules.llm import expiry_loop

            expiry = asyncio.create_task(expiry_loop(app.state.sessions)) if settings.llm_enabled else None
            from pms_api.modules.account_delivery import delivery_loop

            account_delivery = (
                asyncio.create_task(delivery_loop(app.state.sessions, settings))
                if settings.local_auth_enabled
                else None
            )
            from pms_api.modules.invitation_delivery import delivery_loop as invitation_loop

            invitation_delivery = asyncio.create_task(invitation_loop(app.state.sessions, settings))
            from pms_api.modules.speech import retention_loop

            speech_expiry = asyncio.create_task(retention_loop(app.state.sessions, app.state.storage))
            from pms_api.modules.session_queue import expiry_loop as queue_expiry_loop

            queue_expiry = asyncio.create_task(queue_expiry_loop(app.state.sessions))
            from pms_api.modules.session_archives import retention_loop as archive_retention_loop

            archive_retention = asyncio.create_task(
                archive_retention_loop(app.state.sessions, app.state.storage)
            )
            try:
                yield
            finally:
                archive_retention.cancel()
                with suppress(asyncio.CancelledError):
                    await archive_retention
                queue_expiry.cancel()
                with suppress(asyncio.CancelledError):
                    await queue_expiry
                if app.state.speech_tasks:
                    pending = list(app.state.speech_tasks)
                    _, unfinished = await asyncio.wait(pending, timeout=5)
                    for task in unfinished:
                        task.cancel()
                    await asyncio.gather(*pending, return_exceptions=True)
                speech_expiry.cancel()
                with suppress(asyncio.CancelledError):
                    await speech_expiry
                if expiry:
                    expiry.cancel()
                    with suppress(asyncio.CancelledError):
                        await expiry
                invitation_delivery.cancel()
                with suppress(asyncio.CancelledError):
                    await invitation_delivery
                if account_delivery:
                    account_delivery.cancel()
                    with suppress(asyncio.CancelledError):
                        await account_delivery
                await app.state.llm.close()
                await app.state.storage.close()
                await engine.dispose()

    app = FastAPI(
        title="PMS API",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs" if settings.expose_docs or settings.environment in {"local", "test"} else None,
        redoc_url=None,
        openapi_url="/openapi.json"
        if settings.expose_docs or settings.environment in {"local", "test"}
        else None,
    )
    from pms_api.core.rate_limit import RateLimiter

    limiter = RateLimiter()
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    )

    def error(request, status, code, message, details=None):
        return JSONResponse(
            status_code=status,
            content={
                "error": {
                    "code": code,
                    "message": message,
                    "request_id": getattr(request.state, "request_id", None),
                    "details": details,
                }
            },
            headers={
                "Cache-Control": "no-store",
                **({"WWW-Authenticate": "Bearer"} if status == 401 else {}),
            },
        )

    @app.exception_handler(HTTPException)
    async def http_error(request, exception):
        from http import HTTPStatus

        return error(request, exception.status_code, "http_error", HTTPStatus(exception.status_code).phrase)

    @app.exception_handler(AppError)
    async def application_error(request, exception):
        return error(request, exception.status, exception.code, exception.message, exception.details)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exception):
        # Never echo raw inputs: credentials can occur anywhere in request models.
        errors = exception.errors()
        invalid_keys = {tuple(e["loc"][:-1]) for e in errors if e["loc"] and e["loc"][-1] == "[key]"}
        details = []
        for item in errors[:100]:
            location = list(item["loc"])
            # Unknown names and invalid dictionary keys are also untrusted input.
            for prefix in invalid_keys:
                if tuple(location[: len(prefix)]) == prefix:
                    location[len(prefix) - 1] = "<invalid_key>"
            if item["type"] == "extra_forbidden" and location:
                location[-1] = "<unknown_field>"
            details.append({"location": location, "type": item["type"]})
        return error(request, 422, "invalid_request", "Request validation failed", details)

    @app.exception_handler(DBAPIError)
    async def database_error(request, exception):
        code = getattr(exception.orig, "sqlstate", None)
        constraint = getattr(getattr(exception.orig, "diag", None), "constraint_name", None)
        if code == "23505" and constraint in {
            "device_identities_pkey",
            "device_unique_id_global",
            "device_identity_current_registration",
        }:
            return error(
                request, 409, "device_unique_id_exists", "This device unique ID is already registered"
            )
        subscription_errors = {
            "subscription_user_limit": "User capacity is exceeded; deactivate a membership or choose a larger plan",
            "subscription_device_limit": "Device capacity is exceeded; deactivate a device or choose a larger plan",
            "subscription_plan_unavailable": "Select an active subscription plan",
        }
        if code == "23514" and constraint in subscription_errors:
            return error(request, 409, constraint, subscription_errors[constraint])
        if code in {"23505", "23503", "23514", "40001", "40P01", "55P03"}:
            return error(
                request,
                409,
                "state_conflict",
                "The operation conflicts with current data, lifecycle rules, or a concurrent update",
            )
        if code in {"23502", "22001", "22003", "22P02"}:
            return error(request, 422, "invalid_data", "A value violates the database contract")
        logger.error(
            json.dumps({"event": "database_error", "sqlstate": code, "request_id": request.state.request_id})
        )
        return error(request, 503, "database_unavailable", "Database operation is temporarily unavailable")

    @app.exception_handler(Exception)
    async def unexpected_error(request, exception):
        logger.error(
            json.dumps(
                {
                    "event": "unhandled_error",
                    "type": type(exception).__name__,
                    "request_id": getattr(request.state, "request_id", None),
                }
            )
        )
        return error(request, 500, "internal_error", "An unexpected error occurred")

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = str(uuid4())
        start = time.monotonic()
        category = (
            "enrollment"
            if request.url.path == "/api/v1/device/enroll"
            else "authentication"
            if request.url.path.startswith("/api/v1/auth/") and request.method != "GET"
            else "identity"
            if request.url.path == "/api/v1/identity/sync"
            else "general"
        )
        if request.url.path.startswith("/api/v1/") and not limiter.allow(
            (request.client.host if request.client else "unknown", category),
            30 if category != "general" else 600,
        ):
            response = error(request, 429, "rate_limit", "Request rate limit exceeded")
            response.headers["Retry-After"] = "60"
            return response
        if request.method in {"POST", "PUT", "PATCH"} and not request.url.path.startswith(
            "/api/v1/media/local/"
        ):
            body = bytearray()
            body_limit = settings.request_max_bytes
            if request.url.path.endswith("/speech/transcriptions"):
                body_limit = min(4_000_000, settings.speech_max_seconds * 32000 + 4096)
            if "/local-conversation-turns" in request.url.path:
                body_limit = min(body_limit, 128 * 1024)
            if "/training/scenario-drafts" in request.url.path:
                body_limit = min(body_limit, 128 * 1024)
            if request.url.path.endswith("/member-imports/validate"):
                body_limit = min(body_limit, 512 * 1024)
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > body_limit:
                    return error(
                        request, 413, "payload_too_large", "Request exceeds the configured size limit"
                    )
            request._body = bytes(body)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        route = getattr(request.scope.get("route"), "path", "unmatched")
        duration = time.monotonic() - start
        REQUESTS.labels(request.method, route, str(response.status_code)).inc()
        LATENCY.labels(request.method, route).observe(duration)
        logger.info(
            json.dumps(
                {
                    "request_id": request.state.request_id,
                    "method": request.method,
                    "route": route,
                    "status": response.status_code,
                    "duration_ms": round(duration * 1000),
                }
            )
        )
        return response

    @app.get("/health/live", tags=["Health"])
    async def live():
        return {"status": "alive", "service": "pms_api", "version": __version__}

    @app.get("/api/v1/health/ready", tags=["Health"])
    @app.get("/health/ready", tags=["Health"])
    async def ready():
        try:
            async with app.state.sessions() as session:
                if not await check_schema(session):
                    return JSONResponse(
                        status_code=503, content={"status": "not_ready", "reason": "schema_mismatch"}
                    )
        except Exception:
            return JSONResponse(
                status_code=503, content={"status": "not_ready", "reason": "database_unavailable"}
            )
        return {"status": "ready", "service": "pms_api", "version": __version__}

    @app.get("/metrics", include_in_schema=False)
    async def metrics(request: Request):
        token = settings.metrics_token.get_secret_value()
        if not token or not hmac.compare_digest(request.headers.get("authorization", ""), "Bearer " + token):
            return Response(status_code=404)
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    from pms_api.modules import (
        activity,
        auth,
        device_management,
        devices,
        direct_models,
        management,
        manual_subscriptions,
        member_imports,
        model_catalog,
        patient_catalog,
        platform_models,
        subscriptions,
        tenant_members,
        tenant_provisioning,
    )

    for module in (
        auth,
        management,
        devices,
        model_catalog,
        platform_models,
        subscriptions,
        activity,
        direct_models,
        device_management,
        manual_subscriptions,
        member_imports,
        patient_catalog,
        tenant_members,
        tenant_provisioning,
    ):
        app.include_router(module.router, prefix="/api/v1")
    # Processing routes are registered with the same authentication/transaction dependencies.
    from pms_api.modules import (
        initial_setup,
        llm,
        patient_conversations,
        patient_practice,
        processing,
        scenarios,
        session_archives,
        session_queue,
        training,
    )

    app.include_router(initial_setup.router, prefix="/api/v1")
    app.include_router(llm.router, prefix="/api/v1")
    from pms_api.modules import downloads, local_conversation_turns, local_turns, model_routing, speech

    app.include_router(downloads.router, prefix="/api/v1")

    app.include_router(local_conversation_turns.router, prefix="/api/v1")

    app.include_router(local_turns.router, prefix="/api/v1")
    app.include_router(model_routing.router, prefix="/api/v1")
    app.include_router(speech.router, prefix="/api/v1")
    app.include_router(patient_practice.router, prefix="/api/v1")
    app.include_router(patient_conversations.router, prefix="/api/v1")
    app.include_router(processing.router, prefix="/api/v1")
    app.include_router(training.router, prefix="/api/v1")
    from pms_api.modules import inference

    app.include_router(inference.router, prefix="/api/v1")
    app.include_router(session_queue.router, prefix="/api/v1")
    app.include_router(session_archives.router, prefix="/api/v1")
    app.include_router(scenarios.router, prefix="/api/v1")
    return app
