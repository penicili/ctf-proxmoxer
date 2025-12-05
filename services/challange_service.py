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


class ChallengeService:
    """
    Service untuk manajemen Challenge dan memanggil ProxmoxService sesuai kebutuhan
    Business logic utama aplikasi
    """
    
    def __init__(self):
        # TODO: panggil database dan proxmoxservice
        self.proxmox_service = ProxmoxService()
        self.db = SessionLocal()
        pass
    
    def __del__ (self):
        """
        Cleanup close db connection
        """
        self.db.close()
    
    def create_challenge(self, level_id: int, team_name: str) -> list[Dict[str, Any]]:
        """Create challenge

        Args:
            level_id (int): template level challenge CTF
            team_name (str): nama tim

        Returns:
            list[Dict[str, Any]]: Status Message, IP dan port VM
        """
        # TODO: Implement challenge creation logic
        
        # Create VM via ProxmoxService
        vm = self.proxmox_service.create_vm(
            level_id=level_id,
            team=team_name,
            time_limit=60,
            config={}
        )
        
        if vm:
            logger.info(f"Challenge VM created with VMID: {vm['vmid']}")
            return [{
                "status": "success",
                "vmid": vm["vmid"],
                "info": vm["info"]
            }]
            
        # Simpan ke deployment database dan challenge database
        
        return []
    
    def submit_challenge(self, challenge_id: int, flag: str) -> list[Dict[str, Any]]:
        # TODO: Buat challenge submission logic
        return []
    
    def get_all(self) -> list[Dict[str, Any]]:
        # TODO: ambil semua challenge dari database juga vm yang terkati dari proxmoxservice
        return []
    
    
