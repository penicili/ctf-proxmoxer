from pydantic import BaseModel, Field
from typing import Optional
from models.Level import CategoryEnum, DifficultyEnum


class CreateLevelRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    category: CategoryEnum
    difficulty: DifficultyEnum
    description: Optional[str] = None
    points: int = Field(default=100, gt=0)
    template_url: Optional[str] = Field(default=None, max_length=255)
    source_url: Optional[str] = Field(default=None, max_length=500)
    initial_points: int = Field(default=1000, gt=0)
    minimum_points: int = Field(default=100, gt=0)
    decay: int = Field(default=25, gt=0)


class UpdateLevelRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    category: Optional[CategoryEnum] = None
    difficulty: Optional[DifficultyEnum] = None
    description: Optional[str] = None
    points: Optional[int] = Field(default=None, gt=0)
    template_url: Optional[str] = Field(default=None, max_length=255)
    source_url: Optional[str] = Field(default=None, max_length=500)
    is_active: Optional[bool] = None
    initial_points: Optional[int] = Field(default=None, gt=0)
    minimum_points: Optional[int] = Field(default=None, gt=0)
    decay: Optional[int] = Field(default=None, gt=0)