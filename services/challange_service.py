from typing import Dict, Any, List, Optional, Sequence
from datetime import datetime
import random

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from models import Challenge, Deployment, Level
from services.proxmox_service import ProxmoxService
from services.ansible_service import AnsibleService # NEW
from config.settings import Settings
from core.logging import logger
from core.exceptions import VMCreationError, ResourceNotFoundError
from schemas.types.vm_types import VMResult
from schemas.types.challenge_types import ChallengeResult
from schemas.types.ansible_types import AnsiblePlaybookParams, AnsiblePlaybookReturn # NEW

class ChallengeService:
    """
    Service untuk manajemen Challenge dan memanggil ProxmoxService sesuai kebutuhan.
    Business logic utama aplikasi.
    """
    
    def __init__(self, db: Session, proxmox_service: ProxmoxService, ansible_service: AnsibleService, settings: Settings):
        self.db = db
        self.proxmox_service = proxmox_service
        self.ansible_service = ansible_service # NEW
        self.settings = settings
    
    def create_challenge(self, level_id: int, team_name: str) -> ChallengeResult:
        """
        Create challenge implementation.
        """
        vm: Optional[VMResult] = None
        ansible_result: Optional[AnsiblePlaybookReturn] = None # NEW
        try:
            # Create VM via ProxmoxService
            vm = self.proxmox_service.create_vm(
                level_id=level_id,
                team=team_name,
                time_limit=60, # TODO: Move to settings or level config
                config={}
            )

            # --- Ansible Configuration (NEW) ---
            # TODO: Implement a robust way to get the VM's IP address.
            # For now, assuming vm.info.name is resolvable or using a placeholder.
            # Ideally, wait for network (e.g., via Cloud-Init or Proxmox API for IP)
            vm_ssh_target = vm.info.name if vm.info and vm.info.name else f"vmid-{vm.vmid}"
            
            # Generate Flag
            random_flag = ''.join(random.choices(
                self.settings.FLAG_CHARSET, 
                k=self.settings.FLAG_LENGTH
            ))
            flagstring = f"{self.settings.FLAG_PREFIX}{{{random_flag}}}"

            ansible_request = AnsiblePlaybookParams(
                host=vm_ssh_target, # Host for Ansible (placeholder)
                playbook_name="setup_challenge.yml",
                user=self.settings.SSH_USERNAME, # Default SSH user from settings
                private_key=None, # TODO: Implement SSH key management if needed
                extra_vars={"challenge_flag": flagstring,
                            "challenge_flag_path": "/var/www/html/flag.txt",
                            "challenge_repo_url": "some-repo-url",  # TODO: Define challenge repo URL
                           }
            )
            
            logger.info(f"Running Ansible playbook '{ansible_request.playbook_name}' on '{vm_ssh_target}'")
            ansible_result = self.ansible_service.run_playbook(ansible_request)

            if not ansible_result.success:
                logger.error(f"Ansible playbook failed for VM {vm.vmid}. Output: {ansible_result.stdout}")
                # Raise an error, or handle gracefully (e.g., mark challenge as failed config)
                raise VMCreationError(f"Ansible configuration failed for VM {vm.vmid}")
            
            logger.info(f"Ansible configuration complete for VM {vm.vmid}.")
            # --- End Ansible Configuration ---

            # 1. Create Challenge FIRST (Parent)
            new_challenge = Challenge(
                level_id=level_id,
                team=team_name,
                flag=flagstring,
                flag_submitted=False,
                is_active=True
            )
            self.db.add(new_challenge)
            self.db.flush() # Get ID for new_challenge
            
            # 2. Create Deployment (Child) linked to Challenge
            new_deployment = Deployment(
                challenge_id=new_challenge.id,
                vm_id=vm.vmid,
                vm_name=vm.info.name if vm.info and vm.info.name else f"vm-{vm.vmid}",
                # status defaults to PENDING
            )
            
            self.db.add(new_deployment)
            self.db.commit()
            self.db.refresh(new_challenge) # Refresh to load relationship if needed
            
            logger.info(f"Challenge created: {new_challenge.id}, Flag: {new_challenge.flag}")

            return ChallengeResult(
                success=True,
                message="Challenge created successfully",
                challenge_id=new_challenge.id,
                vm_info=vm,
                flag=flagstring # Hanya untuk debug/admin, jangan expose ke user biasa nanti
            )
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error during challenge creation: {e}")
            
            # Cleanup: If VM was created but DB failed or Ansible failed, we must clean up the VM
            if vm:
                try:
                    logger.warning(f"Rolling back VM {vm.vmid} due to error: {e}")
                    self.proxmox_service.stop_vm(vm.vmid)
                    # TODO: Implement destroy_vm in ProxmoxService for full cleanup
                except Exception as cleanup_error:
                    logger.error(f"Failed to cleanup VM {vm.vmid}: {cleanup_error}")
            
            # Re-raise the original error
            raise e
    
    def submit_challenge(self, challenge_id: int, flag: str) -> Dict[str, Any]:
        stmt = select(Challenge).where(Challenge.id == challenge_id)
        challenge = self.db.execute(stmt).scalars().first()
        
        if not challenge:
            raise ResourceNotFoundError(f"Challenge {challenge_id} not found")
        
        if challenge.flag == flag:
            challenge.flag_submitted = True
            challenge.flag_submitted_at = datetime.now()
            
            # Stop VM logic
            stmt_dep = select(Deployment).where(Deployment.challenge_id == challenge_id)
            deployment = self.db.execute(stmt_dep).scalars().first()
            
            if deployment and deployment.vm_id:
                try:
                    self.proxmox_service.stop_vm(deployment.vm_id)
                except Exception as e:
                    logger.error(f"Failed to stop VM after submission: {e}")
            
            self.db.commit()
            return {"success": True, "message": "Flag correct!"}
        else:
            return {"success": False, "message": "Flag incorrect"}
    
    def get_all(self) -> Sequence[Challenge]:
        stmt = select(Challenge).options(joinedload(Challenge.deployment))
        return self.db.execute(stmt).scalars().all()