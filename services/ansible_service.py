import os
import ansible_runner
from typing import Dict, Any
from schemas.types.Ansible_types import AnsiblePlaybookRequest, AnsiblePlaybookResult
from config.settings import Settings
from core.logging import logger

class AnsibleService:
    def __init__(self, settings: Settings):
        self.settings = settings
        # Folder project root (asumsi script ini jalan dari root)
        self.project_dir = os.getcwd()
        self.ansible_dir = os.path.join(self.project_dir, "ansible")
        self.playbook_dir = os.path.join(self.ansible_dir, "playbooks")

    def run_playbook(self, request: AnsiblePlaybookRequest) -> AnsiblePlaybookResult:
        logger.info(f"Preparing to run playbook '{request.playbook_name}' on {request.host}")
        
        # Validasi path playbook
        playbook_path = os.path.join(self.playbook_dir, request.playbook_name)
        if not os.path.exists(playbook_path):
            logger.error(f"Playbook not found: {playbook_path}")
            return AnsiblePlaybookResult(
                success=False,
                status="error",
                rc=1,
                stats={},
                stdout=f"Playbook file not found: {request.playbook_name}"
            )

        # Siapkan Inventory dinamis (Host tunggal)
        inventory_content = {
            "all": {
                "hosts": {
                    request.host: {
                        "ansible_user": request.user,
                        # Pass variable lain jika perlu
                        **request.extra_vars
                    }
                }
            }
        }
        
        # Tambahkan private key jika ada
        ssh_key = None
        if request.private_key:
            ssh_key = request.private_key
        
        # Run Ansible Runner
        try:
            r = ansible_runner.run(
                private_data_dir=self.ansible_dir,
                playbook=request.playbook_name, # Runner mencari di project/playbooks atau relative path
                inventory=inventory_content,
                ssh_key=ssh_key,
                quiet=True, # Supaya tidak nyampah di stdout console app
                json_mode=False
            )
            
            # Parse result
            status = r.status
            rc_value = r.rc if r.rc is not None else 1 # Default to 1 (failure) if rc is None
            stats: Dict[str, Any] = getattr(r, 'stats', {})
            
            # DEBUG LOGGING
            logger.debug(f"Ansible Runner Result - Status: {status}, RC: {r.rc} -> {rc_value}")
            
            # Ambil stdout untuk debugging jika gagal
            stdout_obj = getattr(r, 'stdout', None)
            stdout_output = stdout_obj.read() if stdout_obj and hasattr(stdout_obj, 'read') else ""
            
            success = (status == "successful" and rc_value == 0)
            
            if success:
                logger.info(f"Ansible playbook '{request.playbook_name}' finished successfully.")
            else:
                logger.error(f"Ansible playbook failed. Status: {status}, RC: {rc_value}")

            return AnsiblePlaybookResult(
                success=success,
                status=status,
                rc=rc_value,
                stats=stats or {},
                events=[], # Bisa diisi r.events kalo mau detail banget
                stdout=str(stdout_output)
            )

        except Exception as e:
            logger.exception("Exception while running Ansible")
            return AnsiblePlaybookResult(
                success=False,
                status="exception",
                rc=1,
                stats={},
                stdout=str(e)
            )
