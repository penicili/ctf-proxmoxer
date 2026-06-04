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
    initial_points: int = 1000
    minimum_points: int = 100
    decay: int = 25

    model_config = ConfigDict(from_attributes=True)


class LevelListResponse(BaseModel):
    total: int
    levels: List[LevelResponse]