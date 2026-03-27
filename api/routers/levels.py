from fastapi import APIRouter, HTTPException
from typing import Optional

from api.dependencies import DbSessionDep
from models.Level import Level
from schemas.requests.levels_requests import CreateLevelRequest, UpdateLevelRequest
from schemas.responses.levels_responses import LevelResponse, LevelListResponse

router = APIRouter(
    prefix="/levels",
    tags=["Levels"]
)


@router.get("", response_model=LevelListResponse)
def list_levels(db: DbSessionDep, is_active: Optional[bool] = None):
    query = db.query(Level)
    if is_active is not None:
        query = query.filter(Level.is_active == is_active)
    levels = query.order_by(Level.id).all()
    return LevelListResponse(total=len(levels), levels=levels)


@router.post("", response_model=LevelResponse, status_code=201)
def create_level(db: DbSessionDep, request: CreateLevelRequest):
    level = Level(**request.model_dump())
    db.add(level)
    db.commit()
    db.refresh(level)
    return level


@router.get("/{level_id}", response_model=LevelResponse)
def get_level(db: DbSessionDep, level_id: int):
    level = db.query(Level).filter(Level.id == level_id).first()
    if not level:
        raise HTTPException(status_code=404, detail="Level not found")
    return level


@router.put("/{level_id}", response_model=LevelResponse)
def update_level(db: DbSessionDep, level_id: int, request: UpdateLevelRequest):
    level = db.query(Level).filter(Level.id == level_id).first()
    if not level:
        raise HTTPException(status_code=404, detail="Level not found")
    for field, value in request.model_dump(exclude_unset=True).items():
        setattr(level, field, value)
    db.commit()
    db.refresh(level)
    return level


@router.delete("/{level_id}")
def delete_level(db: DbSessionDep, level_id: int):
    level = db.query(Level).filter(Level.id == level_id).first()
    if not level:
        raise HTTPException(status_code=404, detail="Level not found")
    level.is_active = False
    db.commit()
    return {"message": "Level deactivated"}
