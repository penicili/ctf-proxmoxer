from fastapi import APIRouter, HTTPException
from api.dependencies import ProxmoxServiceDep
from core.logging import logger

router = APIRouter(
    prefix="/vms",
    tags=["Virtual Machines"]
)

@router.get("")
def list_vms(service: ProxmoxServiceDep):
    """List all VMs/Containers"""
    try:
        vms = service.list_vms()
        return {
            "total": len(vms),
            "vms": vms
        }
    except Exception as e:
        logger.error(f"Failed to list VMs: {e}")
        raise HTTPException(status_code=503, detail="Proxmox unavailable")
