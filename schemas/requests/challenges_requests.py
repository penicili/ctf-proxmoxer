from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Dict, Any

class CreateChallengeRequest(BaseModel):
    """Request body untuk membuat challenge baru"""
    level_id: int = Field(..., gt=0, description="ID level yang akan di-deploy")
    team_name: str = Field(..., min_length=1, max_length=100, description="Nama tim")
    vm_config: Optional[Dict[str, Any]] = Field(default=None, description="Konfigurasi VM custom (optional)")
    
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "level_id": 1,
            "team_name": "TeamAlpha",
            "vm_config": {
                "memory": 2048,
                "cores": 2,
                "template_vmid": 9000
            }
        }
    })

class SubmitFlagRequest(BaseModel):
    """Request body untuk submit flag"""
    flag: str = Field(..., min_length=1, description="Flag yang akan di-submit")
    
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "flag": "CTF{example_flag_here}"
        }
    })
