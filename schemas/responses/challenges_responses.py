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
    terminated_at: Optional[datetime] = None

    # CTFd challenge ID (set setelah finalize)
    ctfd_id: Optional[int] = None

    # Access info (NAT port forwarding)
    access_ssh: Optional[str] = None   # e.g. "ssh user@192.168.1.102 -p 22201"
    access_http: Optional[str] = None  # e.g. "http://192.168.1.102:80201"
    
    model_config = ConfigDict(from_attributes=True)

class CreateChallengeResult(BaseModel):
    """Hasil deploy untuk satu tim"""
    team: str
    challenge_id: int
    flag: Optional[str] = None
    skipped: bool = False
    skip_reason: Optional[str] = None  # alasan jika di-skip (misal: sudah ada deployment aktif)


class CreateChallengeResponse(BaseModel):
    """Response untuk pembuatan challenge — satu atau beberapa tim sekaligus"""
    success: bool
    message: str
    results: List[CreateChallengeResult]  # hasil per tim
    deployed: int   # jumlah tim yang berhasil di-queue
    skipped: int    # jumlah tim yang di-skip

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
