from fastapi import FastAPI
from contextlib import asynccontextmanager

from config.settings import settings
from core import logger, engine, Base
from models import Level, Challenge, Deployment
from services import ProxmoxService


# Global proxmox instance
proxmox_service = ProxmoxService()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager untuk startup dan shutdown"""
    # Startup
    logger.info("Starting CTF Platform...")
    logger.info(f"Creating database tables...")
    Base.metadata.create_all(bind=engine)
    logger.success("Database initialized successfully!")
    
    # Connect to Proxmox
    logger.info("Connecting to Proxmox...")
    if proxmox_service.connect():
        logger.success("Proxmox connection established!")
    else:
        logger.warning("Failed to connect to Proxmox - some features will be unavailable")
    
    yield
    
    # Shutdown
    logger.info("Shutting down CTF Platform...")
    # proxmox_service.disconnect()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    debug=settings.DEBUG,
    lifespan=lifespan,
)


@app.get("/")
def root():
    """Health check endpoint"""
    return {
        "message": "CTF Platform API",
        "version": settings.VERSION,
        "status": "running"
    }


@app.get("/api/health")
def health_check():
    """Detailed health check"""
    proxmox_status = "connected" if proxmox_service.is_connected() else "disconnected"
    
    return {
        "status": "healthy",
        "database": "connected",
        "proxmox": proxmox_status,
    }


@app.get("/api/vms")
def list_vms():
    """List all VMs/Containers"""
    if not proxmox_service.is_connected():
        return {
            "error": "Proxmox not connected",
            "vms": []
        }
    
    vms = proxmox_service.list_vms()
    return {
        "total": len(vms),
        "vms": vms
    }