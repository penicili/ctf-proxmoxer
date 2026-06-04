from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import Optional, Dict, Any, List

class CreateChallengeRequest(BaseModel):
    """
    Request body untuk membuat challenge baru.
    Mendukung deploy ke satu atau beberapa tim sekaligus via team_names.
    """
    level_id: int = Field(..., gt=0, description="ID level yang akan di-deploy")
    team_names: List[str] = Field(..., min_length=1, description="Daftar nama tim (minimal 1)")
    vm_config: Optional[Dict[str, Any]] = Field(default=None, description="Konfigurasi VM custom (optional)")

    @field_validator("team_names")
    @classmethod
    def team_names_not_empty(cls, v: List[str]) -> List[str]:
        cleaned = [t.strip() for t in v if t.strip()]
        if not cleaned:
            raise ValueError("team_names harus berisi minimal satu nama tim")
        return cleaned

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "level_id": 1,
            "team_names": ["TeamAlpha", "TeamBeta"],
            "vm_config": {
                "memory": 2048,
                "cores": 2,
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
