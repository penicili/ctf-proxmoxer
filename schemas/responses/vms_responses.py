from pydantic import BaseModel, ConfigDict
from typing import List, Dict, Any, Optional

class VMInfoResponse(BaseModel):
    """Response model untuk VM info"""
    vmid: int
    name: Optional[str] = None
    status: Optional[str] = None
    type: Optional[str] = None  # 'qemu' or 'lxc'
    node: Optional[str] = None
    cpus: Optional[int] = None
    memory: Optional[int] = None
    
    # Allow extra fields from Proxmox API
    model_config = ConfigDict(extra='allow')

class VMListResponse(BaseModel):
    """Response untuk list VMs"""
    total: int
    vms: List[Dict[str, Any]]
    
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "total": 2,
            "vms": [
                {"vmid": 1001, "name": "TeamAlpha-1-1001", "status": "running"},
                {"vmid": 1002, "name": "TeamBeta-2-1002", "status": "stopped"}
            ]
        }
    })
