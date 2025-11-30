"""FastAPI application entry point."""
import os
import logging
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.api.auth_api import router as auth_router
from app.api.courses_api import router as courses_router
from app.db.session import init_db, get_db
from app.core.config import settings
from app.core.errors import register_exception_handlers

logger = logging.getLogger(__name__)

# Configure logging based on environment
logging.basicConfig(
    level=logging.DEBUG if settings.ENVIRONMENT == "development" else logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)

# Initialize database tables
init_db()

app = FastAPI(
    title="Bitcoin Academy API",
    version="1.0.0",
    description="AI-Tutor API for Bitcoin Academy platform",
    # Disable docs in production for security
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
    openapi_url="/openapi.json" if settings.ENVIRONMENT != "production" else None,
)

# Add rate limiter state to app
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Register global exception handlers for security
register_exception_handlers(app)

# Parse CORS origins from environment variable
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
CORS_ORIGINS = [origin.strip() for origin in CORS_ORIGINS if origin.strip()]

logger.info(f"CORS Origins configured: {CORS_ORIGINS}")

# Security: Trusted Host middleware (production)
if settings.ENVIRONMENT == "production":
    ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "localhost").split(",")
    ALLOWED_HOSTS = [host.strip() for host in ALLOWED_HOSTS if host.strip()]
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
    allow_headers=["Content-Type", "Authorization"],  # Explicit headers only
    max_age=600,  # Cache preflight requests for 10 minutes
    expose_headers=["Content-Range", "X-Content-Range"],
)

# Include routers
app.include_router(auth_router)
app.include_router(courses_router)


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
def health_check():
    """Health check endpoint with database connectivity test."""
    health_status = {
        "status": "healthy",
        "environment": settings.ENVIRONMENT,
        "database": "unknown",
    }

    # Check database connectivity
    try:
        db = next(get_db())
        db.execute("SELECT 1")
        health_status["database"] = "connected"
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        health_status["database"] = "disconnected"
        health_status["status"] = "degraded"

    return health_status
