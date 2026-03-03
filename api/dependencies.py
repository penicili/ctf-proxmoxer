# dependencies_compact.py
from typing import Annotated
from fastapi import Depends
from sqlalchemy.orm import Session

from config.settings import settings
from core.database import get_db
from services.proxmox_service import ProxmoxService
from services.ansible_service import AnsibleService
from services.challenge_service import ChallengeService

# Type aliases
SettingsDep = Annotated[dict, Depends(lambda: settings)]
DbSessionDep = Annotated[Session, Depends(get_db)]

# Service dependencies
ProxmoxServiceDep = Annotated[ProxmoxService, Depends(lambda: ProxmoxService(settings))]
AnsibleServiceDep = Annotated[AnsibleService, Depends(lambda: AnsibleService(settings))]

def get_challenge_service(
    db: DbSessionDep,
    proxmox: ProxmoxServiceDep,
    ansible: AnsibleServiceDep,
) -> ChallengeService:
    """Get ChallengeService instance"""
    return ChallengeService(db, proxmox, ansible, settings)

ChallengeServiceDep = Annotated[ChallengeService, Depends(get_challenge_service)]