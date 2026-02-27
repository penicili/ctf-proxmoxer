from typing import Annotated
from fastapi import Depends
from sqlalchemy.orm import Session

from config.settings import Settings, settings
from core.database import get_db
from services.proxmox_service import ProxmoxService
from services.ansible_service import AnsibleService
from services.challenge_service import ChallengeService


def get_settings() -> Settings:
    return settings

def get_proxmox_service(
    settings: Settings = Depends(get_settings)
) -> ProxmoxService:
    return ProxmoxService(settings)

def get_ansible_service(
    settings: Settings = Depends(get_settings)
) -> AnsibleService:
    return AnsibleService(settings)

def get_challenge_service(
    db: Session = Depends(get_db),
    proxmox_service: ProxmoxService = Depends(get_proxmox_service),
    ansible_service: AnsibleService = Depends(get_ansible_service),
    settings: Settings = Depends(get_settings),
) -> ChallengeService:
    return ChallengeService(db, proxmox_service, ansible_service, settings)

ChallengeServiceDep = Annotated[ChallengeService, Depends(get_challenge_service)]
ProxmoxServiceDep = Annotated[ProxmoxService, Depends(get_proxmox_service)]