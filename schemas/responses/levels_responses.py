from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime


class LevelResponse(BaseModel):
    id: int
    name: str
    category: str
    difficulty: str
    description: Optional[str] = None
    points: int
    template_url: Optional[str] = None
    source_url: Optional[str] = None
    prepare_status: str = "none"
    prepare_error: Optional[str] = None
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LevelListResponse(BaseModel):
    total: int
    levels: List[LevelResponse]