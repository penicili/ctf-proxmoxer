from pydantic import BaseModel
from typing import Optional
from .vm_types import VMResult

class ChallengeResult(BaseModel):
    """Hasil operasi pembuatan Challenge"""
    success: bool
    message: str
    challenge_id: int
    vm_info: Optional[VMResult] = None # Bisa None jika challenge gagal dibuat (meski biasanya raise Error)
    flag: Optional[str] = None
