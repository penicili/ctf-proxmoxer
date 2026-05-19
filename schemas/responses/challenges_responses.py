from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime
from schemas.types.Vm_types import VMResult

class ChallengeResponse(BaseModel):
    """Response model untuk single challenge"""
    id: int
    level_id: int
    team: str
    flag: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    # Level info
    level_name: Optional[str] = None

    # Deployment info (optional)
    deployment_status: Optional[str] = None
    vm_id: Optional[int] = None
    vm_name: Optional[str] = None
    vm_ip: Optional[str] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None

    # Access info (NAT port forwarding)
    access_ssh: Optional[str] = None   # e.g. "ssh user@192.168.1.102 -p 22201"
    access_http: Optional[str] = None  # e.g. "http://192.168.1.102:80201"
    
    model_config = ConfigDict(from_attributes=True)

class CreateChallengeResponse(BaseModel):
    """Response untuk pembuatan challenge baru"""
    success: bool
    message: str
    challenge_id: int
    vm_info: Optional[VMResult] = None
    flag: Optional[str] = None
    
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "success": True,
            "message": "Challenge created successfully",
            "challenge_id": 42,
            "flag": "CTF{generated_flag}",
            "vm_info": {
                "status": "success",
                "vmid": 1001,
                "info": {"name": "TeamAlpha-1-1001"}
            }
        }
    })

class ChallengeListResponse(BaseModel):
    """Response untuk list challenges"""
    total: int
    challenges: List[ChallengeResponse]
    
class SubmitFlagResponse(BaseModel):
    """Response untuk flag submission"""
    success: bool
    message: str
    correct: bool
    submitted_at: Optional[datetime] = None
    
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "success": True,
            "message": "Flag correct!",
            "correct": True,
            "submitted_at": "2025-12-16T10:30:00"
        }
    })
