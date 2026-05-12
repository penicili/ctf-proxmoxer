import socket
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from config.settings import settings
from core.database import engine, Base
from core.logging import logger

# Import Routers
from api.routers import health, playbook, levels, challenges


def _ping_host(host: str, port: int = 22, timeout: int = 3) -> bool:
    """TCP check ke host:port, return True jika reachable."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager untuk startup dan shutdown"""
    # Startup
    logger.info("Starting CTF Platform...")
    logger.info(f"Creating database tables...")
    Base.metadata.create_all(bind=engine)
    logger.success("Database initialized successfully!")

    # health check ke pve, CI runner use DHCP so no check for now
    pve_ok = _ping_host(settings.PROXMOX_HOST)
    # ci_ok  = _ping_host(settings.CI_RUNNER_IP)
    logger.info(f"PVE ({settings.PROXMOX_HOST}): {'reachable' if pve_ok else 'UNREACHABLE'}")
    # logger.info(f"CI Runner ({settings.CI_RUNNER_IP}): {'reachable' if ci_ok else 'UNREACHABLE'}")
    if not pve_ok :
        logger.warning("One or more infrastructure components are unreachable at startup")
    
    yield
    
    # Shutdown
    logger.info("Shutting down CTF Platform...")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    debug=settings.DEBUG,
    lifespan=lifespan,
)

# CORS — allow plugin CTFd (beda port) untuk akses backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register Routers
app.include_router(health.router,      prefix="/api/v1")
app.include_router(levels.router,      prefix="/api/v1")
app.include_router(challenges.router,  prefix="/api/v1")
app.include_router(playbook.router,    prefix="/api")

@app.get("/")
def root():
    """Health check endpoint"""
    return {
        "message": "CTF Platform API",
        "version": settings.VERSION,
        "status": "running"
    }