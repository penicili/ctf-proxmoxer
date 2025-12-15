from fastapi import FastAPI
from contextlib import asynccontextmanager

from config.settings import settings
from core.database import engine, Base
from core.logging import logger

# Import Routers
from api.routers import challenges, vms, health

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager untuk startup dan shutdown"""
    # Startup
    logger.info("Starting CTF Platform...")
    logger.info(f"Creating database tables...")
    Base.metadata.create_all(bind=engine)
    logger.success("Database initialized successfully!")
    
    yield
    
    # Shutdown
    logger.info("Shutting down CTF Platform...")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    debug=settings.DEBUG,
    lifespan=lifespan,
)

# Register Routers
app.include_router(challenges.router, prefix="/api")
app.include_router(vms.router, prefix="/api")
app.include_router(health.router, prefix="/api")

@app.get("/")
def root():
    """Health check endpoint"""
    return {
        "message": "CTF Platform API",
        "version": settings.VERSION,
        "status": "running"
    }