from typing import Annotated
from fastapi import Depends
from sqlalchemy.orm import Session

from config.settings import settings
from core.database import get_db
from services.proxmox_service import ProxmoxService
from services.ansible_service import AnsibleService
from services.challange_service import ChallengeService

# Global Service Instances
_proxmox_service = ProxmoxService(settings)
_ansible_service = AnsibleService(settings)

def get_proxmox_service() -> ProxmoxService:
    return _proxmox_service

def get_ansible_service() -> AnsibleService:
    return _ansible_service

def get_challenge_service(
    db: Session = Depends(get_db),
    proxmox_service: ProxmoxService = Depends(get_proxmox_service),
    ansible_service: AnsibleService = Depends(get_ansible_service)
) -> ChallengeService:
    return ChallengeService(db, proxmox_service, ansible_service, settings)

# Type Aliases for easy injection
ChallengeServiceDep = Annotated[ChallengeService, Depends(get_challenge_service)]
ProxmoxServiceDep = Annotated[ProxmoxService, Depends(get_proxmox_service)]
