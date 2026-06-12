"""FastAPI application entry point."""
import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text

from app.api.auth_api import router as auth_router
from app.api.certificates_api import router as certificates_router
from app.api.chat_api import router as chat_router
from app.api.courses_api import router as courses_router
from app.api.documents_api import router as documents_router
from app.api.feedback_api import router as feedback_router
from app.api.progress_api import router as progress_router
from app.api.outline_api import router as outline_router
from app.api.quizzes_api import router as quizzes_router
from app.api.study_api import router as study_router
from app.db.session import init_db, get_db
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.rate_limit import limiter
from app.middleware.security import (
    MaxBodySizeMiddleware,
    RequestIDMiddleware,
    SecurityHeadersMiddleware,
)

logger = logging.getLogger(__name__)

_log_level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
logging.basicConfig(
    level=_log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
# Keep third-party chatter out of the console unless LOG_LEVEL=DEBUG
if _log_level > logging.DEBUG:
    for _noisy in ("sqlalchemy.engine", "httpx", "httpcore", "chromadb", "fastembed", "hpack"):
        logging.getLogger(_noisy).setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        init_db()
    except Exception:
        logger.critical("Database initialisation failed — cannot start", exc_info=True)
        raise

    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        from arq.connections import create_pool, RedisSettings
        app.state.arq_pool = await create_pool(RedisSettings.from_dsn(redis_url))
        logger.info("ARQ pool connected to %s", redis_url)
    else:
        app.state.arq_pool = None
        logger.warning("REDIS_URL not set — document ingestion runs as BackgroundTask (no ARQ)")
    yield
    pool = getattr(app.state, "arq_pool", None)
    if pool is not None:
        await pool.close()


app = FastAPI(
    title="Bitcoin Academy API",
    version="1.0.0",
    description="AI-Tutor API for Bitcoin Academy platform",
    lifespan=lifespan,
    # Disable docs in production for security
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
    openapi_url="/openapi.json" if settings.ENVIRONMENT != "production" else None,
)

# Add rate limiter state to app
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

# Register global exception handlers for security
register_exception_handlers(app)

# =============================================================================
# Security Middleware Stack (order matters - first added = last executed)
# =============================================================================

# 1. Body size limit — reject oversized requests before reading the body
app.add_middleware(MaxBodySizeMiddleware)

# 2. Security Headers - adds security headers to all responses
app.add_middleware(SecurityHeadersMiddleware, environment=settings.ENVIRONMENT)

# 3. Request ID - adds unique ID to each request for tracing
app.add_middleware(RequestIDMiddleware)

# =============================================================================
# CORS Configuration
# =============================================================================

# Parse CORS origins from environment variable
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "").split(",") if settings.ENVIRONMENT == "production" else os.getenv(
    "CORS_ORIGINS", "http://localhost:3000").split(",")
CORS_ORIGINS = [origin.strip() for origin in CORS_ORIGINS if origin.strip()]

# Security: Fail if CORS not configured in production
if settings.ENVIRONMENT == "production" and not CORS_ORIGINS:
    raise ValueError(
        "❌ CRITICAL: CORS_ORIGINS must be configured in production. "
        "Set CORS_ORIGINS environment variable with allowed origins."
    )

logger.info(f"CORS Origins configured: {CORS_ORIGINS}")

# Security: Trusted Host middleware (production)
if settings.ENVIRONMENT == "production":
    ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "").split(",")
    ALLOWED_HOSTS = [host.strip() for host in ALLOWED_HOSTS if host.strip()]

    if not ALLOWED_HOSTS:
        raise ValueError(
            "❌ CRITICAL: ALLOWED_HOSTS must be configured in production. "
            "Set ALLOWED_HOSTS environment variable."
        )

    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=ALLOWED_HOSTS,
    )

# Configure CORS with strict security settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE",
                   "OPTIONS"],  # Explicit methods only
    allow_headers=["Content-Type", "Authorization",
                   "X-Request-ID"],  # Include request ID
    max_age=600,  # Cache preflight requests for 10 minutes
    expose_headers=["Content-Range", "X-Content-Range", "X-Request-ID"],
)

# Include routers
app.include_router(auth_router)
app.include_router(certificates_router)
app.include_router(chat_router)
app.include_router(courses_router)
app.include_router(documents_router)
app.include_router(feedback_router)
app.include_router(progress_router)
app.include_router(outline_router)
app.include_router(quizzes_router)
app.include_router(study_router)

if settings.DEBUG_MODE:
    from app.api.debug_api import router as debug_router
    app.include_router(debug_router)
    logger.info("Debug API enabled at /api/debug/*")


@app.get("/", tags=["Root"])
def root():
    """Root endpoint with API information."""
    return {
        "name": "Bitcoin Academy API",
        "version": "1.0.0",
        "docs": "/docs" if settings.ENVIRONMENT != "production" else None,
        "health": "/health",
        "message": "This is a REST API backend. For the web interface, visit http://localhost:3000",
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint — tests DB, QVAC reachability, and cache mode."""
    import httpx as _httpx

    health_status: dict = {
        "status": "healthy",
        "database": "unknown",
        "qvac": "unknown",
        "cache": "unknown",
    }

    # ── Database ──────────────────────────────────────────────────
    try:
        gen = get_db()
        db = next(gen)
        try:
            db.execute(text("SELECT 1"))
            health_status["database"] = "connected"
        finally:
            gen.close()
    except Exception as e:
        logger.error("Database health check failed: %s", e)
        health_status["database"] = "disconnected"
        health_status["status"] = "degraded"

    # ── QVAC ─────────────────────────────────────────────────────
    qvac_url = os.getenv("QVAC_SERVICE_URL", "http://localhost:3001")
    try:
        async with _httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{qvac_url}/health")
            health_status["qvac"] = "connected" if resp.status_code < 400 else "unreachable"
    except Exception:
        health_status["qvac"] = "unreachable"

    if health_status["qvac"] == "unreachable":
        health_status["status"] = "degraded"

    # ── Cache ─────────────────────────────────────────────────────
    health_status["cache"] = "redis" if os.getenv("REDIS_URL") else "in-memory"

    return health_status
