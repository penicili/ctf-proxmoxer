from fastapi import APIRouter
from config.settings import settings
from api.dependencies import ProxmoxServiceDep

router = APIRouter(
    prefix="/health",
    tags=["System"]
)

@router.get("")
def health_check(proxmox_service: ProxmoxServiceDep):
    """Detailed health check"""
    # Check Proxmox Connectivity by verifying version
    proxmox_status = "connected"
    try:
        if proxmox_service.proxmox:
            proxmox_service.proxmox.version.get()
        else:
            proxmox_service._ensure_connected()
    except Exception:
        proxmox_status = "disconnected"
    
    return {
        "status": "healthy",
        "database": "connected", # Assumed if app is running
        "proxmox": proxmox_status,
        "version": settings.VERSION
    }
