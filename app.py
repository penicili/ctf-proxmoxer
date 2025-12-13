from fastapi import FastAPI, Depends, HTTPException
from contextlib import asynccontextmanager
from sqlalchemy.orm import Session
from typing import List

from config.settings import settings
from core.database import engine, Base, get_db
from core.logging import logger
from core.exceptions import ProxmoxConnectionError, ResourceNotFoundError

from services.proxmox_service import ProxmoxService
from services.ansible_service import AnsibleService
from services.challange_service import ChallengeService
from schemas.types.Challenge_types import ChallengeResult

# Initialize Core Services (Global)
# These services are stateless or manage their own connection pools
proxmox_service = ProxmoxService(settings)
ansible_service = AnsibleService(settings)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager untuk startup dan shutdown"""
    # Startup
    logger.info("Starting CTF Platform...")
    logger.info(f"Creating database tables...")
    Base.metadata.create_all(bind=engine)
    logger.success("Database initialized successfully!")
    
    # Proxmox connection is now lazy/on-demand, no need to connect explicitly here
    
    yield
    
    # Shutdown
    logger.info("Shutting down CTF Platform...")


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
    # Check Proxmox Connectivity by verifying version
    proxmox_status = "connected"
    try:
        proxmox_service.proxmox.version.get() if proxmox_service.proxmox else proxmox_service._ensure_connected()
    except Exception:
        proxmox_status = "disconnected"
    
    return {
        "status": "healthy",
        "database": "connected", # Assumed if app is running
        "proxmox": proxmox_status,
    }


@app.get("/api/vms")
def list_vms():
    """List all VMs/Containers"""
    try:
        vms = proxmox_service.list_vms()
        return {
            "total": len(vms),
            "vms": vms
        }
    except Exception as e:
        logger.error(f"Failed to list VMs: {e}")
        raise HTTPException(status_code=503, detail="Proxmox unavailable")

@app.post("/api/challenges", response_model=ChallengeResult)
def create_challenge(level_id: int, team_name: str, db: Session = Depends(get_db)):
    """
    Create a new challenge (Provision VM + Ansible Config)
    """
    # Initialize ChallengeService with request-scoped DB session
    service = ChallengeService(db, proxmox_service, ansible_service, settings)
    
    try:
        result = service.create_challenge(level_id, team_name)
        return result
    except Exception as e:
        logger.exception("Failed to create challenge")
        raise HTTPException(status_code=500, detail=str(e))