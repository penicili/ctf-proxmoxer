"""
Docstring for services.challange_service

Manajemen challange yang telah dibuat, status challange serta vm yang terkait
"""
from typing import Dict, Any, List
from datetime import datetime
from models import Challenge, Deployment, Level
from services.proxmox_service import ProxmoxService
from core.logging import logger
from core.database import SessionLocal
from config.settings import settings
import random

class ChallengeService:
    """
    Service untuk manajemen Challenge dan memanggil ProxmoxService sesuai kebutuhan
    Business logic utama aplikasi
    """
    
    def __init__(self):
        # panggil database dan proxmoxservice
        self.proxmox_service = ProxmoxService()
        self.db = SessionLocal()
    
    def __del__ (self):
        """
        Cleanup close db connection
        """
        self.db.close()
    
    def create_challenge(self, level_id: int, team_name: str) -> Dict[str, Any]:
        """Create challenge

        Args:
            level_id (int): template level challenge CTF
            team_name (str): nama tim

        Returns:
            Dict[str, Any]: info challenge dan vm terkait
        """
        
        # Create VM via ProxmoxService
        vm = self.proxmox_service.create_vm(
            level_id=level_id,
            team=team_name,
            time_limit=60,
            config={}
        )
        
        if not vm:
            logger.error(f"Failed to create VM for team '{team_name}' and level '{level_id}'")
            raise Exception("VM creation failed")
        

        # Create Deployment record di db
        
        new_deployment = Deployment(
            level_id=level_id,
            team=team_name,
            vm_id=vm['vmid'],
            is_active=True
        )
        
        self.db.add(new_deployment)
        self.db.commit()
        self.db.refresh(new_deployment)
        
        # Randomize flag
        flag_length = settings.FLAG_LENGTH
        flag_charset = settings.FLAG_CHARSET
        flag_prefix = settings.FLAG_PREFIX
        random_flag = ''.join(random.choices(flag_charset, k=flag_length))
        flagstring = f"{flag_prefix}{{{random_flag}}}"
        
        new_challenge = Challenge(
            level_id=level_id,
            team=team_name,
            flag=flagstring,
            flag_submitted=False,
            is_active=True
        )
        
        self.db.add(new_challenge)
        self.db.commit()
        self.db.refresh(new_challenge)
        logger.info(f"Challenge created for team '{team_name}' with ID: {new_challenge.id} and flag: {new_challenge.flag}")


        # TODO: return apalah ini biar nggak kosong gitu dianuin
        return {
            "message": "Challenge created successfully",
            "challenge_id": new_challenge.id,
            "vm_info": vm
        }
    
    def submit_challenge(self, challenge_id: int, flag: str) -> Dict[str, Any]:
        # TODO: Buat challenge submission logic
        return {}
    
    def get_all(self) -> Dict[str, Any]:
        # TODO: ambil semua challenge dari database juga vm yang terkati dari proxmoxservice
        return {}
    
    
