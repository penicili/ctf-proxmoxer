from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List

from core.logging import logger
from schemas.requests import CreateChallengeRequest, SubmitFlagRequest
from schemas.responses import CreateChallengeResponse, ChallengeListResponse, SubmitFlagResponse
from api.dependencies import ChallengeServiceDep

router = APIRouter(
    prefix="/challenges",
    tags=["Challenges"]
)

@router.post("", response_model=CreateChallengeResponse, status_code=201)
def create_challenge(request: CreateChallengeRequest, service: ChallengeServiceDep):
    """
    Create a new challenge (Provision VM + Ansible Config)
    """
    try:
        result = service.create_challenge(request.level_id, request.team_name)
        return result
    except Exception as e:
        logger.exception("Failed to create challenge")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("", response_model=ChallengeListResponse)
def list_challenges(service: ChallengeServiceDep):
    """List all challenges"""
    challenges = service.get_all()
    return {
        "total": len(challenges),
        "challenges": challenges
    }

@router.post("/{challenge_id}/submit", response_model=SubmitFlagResponse)
def submit_flag(challenge_id: int, request: SubmitFlagRequest, service: ChallengeServiceDep):
    """Submit a flag for a challenge"""
    try:
        return service.submit_challenge(challenge_id, request.flag)
    except Exception as e:
        # ResourceNotFoundError is handled generally, but for now we catch all
        # Ideally add specific exception handlers in main app
        logger.error(f"Submission error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
