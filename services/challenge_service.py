from typing import Dict, Any, List, Optional, Sequence
from datetime import datetime
import random

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from models import Challenge, Deployment, Level
from services.proxmox_service import ProxmoxService
from services.ansible_service import AnsibleService  # NEW
from config.settings import Settings
from core.logging import logger
from core.exceptions import VMCreationError, ResourceNotFoundError
from schemas.types.Vm_types import VMResult
from schemas.types.challenge_types import ChallengeResult
from schemas.types.ansible_types import AnsiblePlaybookParams, AnsiblePlaybookReturn  # NEW


class ChallengeService:
    """
    Service untuk manajemen Challenge dan memanggil ProxmoxService sesuai kebutuhan.
    Business logic utama aplikasi.
    """

    def __init__(self, db: Session, proxmox_service: ProxmoxService, ansible_service: AnsibleService,
                 settings: Settings):
        self.db = db
        self.proxmox_service = proxmox_service
        self.ansible_service = ansible_service
        self.settings = settings

    def create_challenge(self):
        pass

    def submit_challenge(self):
        pass