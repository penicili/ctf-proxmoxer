from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List

from core.logging import logger
from schemas.types.challenge_types import ChallengeResult
from api.dependencies import ChallengeServiceDep

router = APIRouter(
    prefix="/challenges",
    tags=["Challenges"]
)

@router.post("", response_model=ChallengeResult)
def create_challenge(level_id: int, team_name: str, service: ChallengeServiceDep):
    """
    Create a new challenge (Provision VM + Ansible Config)
    """
    try:
        result = service.create_challenge(level_id, team_name)
        return result
    except Exception as e:
        logger.exception("Failed to create challenge")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("")
def list_challenges(service: ChallengeServiceDep):
    """List all challenges"""
    return service.get_all()

@router.post("/{challenge_id}/submit")
def submit_flag(challenge_id: int, flag: str, service: ChallengeServiceDep):
    """Submit a flag for a challenge"""
    try:
        return service.submit_challenge(challenge_id, flag)
    except Exception as e:
        # ResourceNotFoundError is handled generally, but for now we catch all
        # Ideally add specific exception handlers in main app
        logger.error(f"Submission error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
