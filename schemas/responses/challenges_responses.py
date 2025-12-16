from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime
from schemas.types.vm_types import VMResult

class ChallengeResponse(BaseModel):
    """Response model untuk single challenge"""
    id: int
    level_id: int
    team: str
    flag: Optional[str] = None
    flag_submitted: bool
    flag_submitted_at: Optional[datetime] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    # Deployment info (optional)
    deployment_status: Optional[str] = None
    vm_id: Optional[int] = None
    vm_name: Optional[str] = None
    vm_ip: Optional[str] = None
    
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
