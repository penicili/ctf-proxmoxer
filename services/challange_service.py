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
from sqlalchemy import select
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
        
        # TODO: ntar flag nggak bakal digenerate oleh backend, tapi sama vm nya sendiri
        # TODO: buat api yang dipanggil vm buat ngereport ketika flag nya udah disubmit
        # TODO: buat service buat submit flag ke vm/container via TCP atau semacemnya
        
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
            "status": "success",
            "message": "Challenge created successfully",
            "challenge_id": new_challenge.id,
            "vm_info": vm
        }
    
    def submit_challenge(self, challenge_id: int, flag: str) -> Dict[str, Any]:
        # TODO: Buat challenge submission logic
        
        # cari challenge di db
        stmt = select(Challenge).where(Challenge.id == challenge_id)
        challenge = self.db.execute(stmt).scalars().first()
        
        if challenge is None:
            raise ValueError("Challenge not found")
        isCorrectFlag = (challenge.flag == flag)
        
        # kalau flag bener, kita update flag_submitted jadi true dan matiin vm nya
        if isCorrectFlag:
            challenge.flag_submitted = True
            challenge.flag_submitted_at = datetime.now()
            self.db.commit()
            # cari deployment yang terkait
            stmt = select(Deployment).where(Deployment.challenge_id == challenge_id)
            deployment = self.db.execute(stmt).scalars().first()
            if deployment:
                # matiin vm via proxmoxservice
                self.proxmox_service.stop_vm(deployment.vm_id)
        
            
            
            
        
        
        # kalo sesuai, update flag_submitted jadi true
        return {}
    
    def get_all(self) -> Dict[str, Any]:
        # TODO: ambil semua challenge dari database juga vm yang terkati dari proxmoxservice
        return {}
    
    
