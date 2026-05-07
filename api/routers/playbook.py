from fastapi import APIRouter, Request
from pydantic import BaseModel, field_validator
from loguru import logger

from api.dependencies import AnsibleServiceDep

router = APIRouter(
    prefix="/playbooks",
    tags=["Ansible Playbooks Management"]
)

class RunPlaybookRequest(BaseModel):
    playbook_name: str
    host: str

@router.get("/list")
def list_playbooks(ansible_service: AnsibleServiceDep):
    """List available Ansible playbooks"""
    try:
        playbooks = ansible_service.get_playbooks()
        return {
            "total": len(playbooks),
            "playbooks": playbooks
        }
    except Exception as e:
        return {
            "total": 0,
            "playbooks": [],
            "error": str(e)
        }

@router.post("/create")
def create_playbook(ansible_service: AnsibleServiceDep):
    """Create a new Ansible playbook (placeholder)"""
    # TODO: Implement playbook creation logic
    # This is a placeholder for future implementation
    return {
        "message": "Playbook creation endpoint - to be implemented"
    }

@router.post("/run")
def run_playbook(ansible_service: AnsibleServiceDep, request: RunPlaybookRequest):
    """Run an Ansible playbook"""
    # TODO: sesuaikan dengan service yang udah fix, terutama parameters nya
    ansible_service.run_playbook(request.playbook_name, request.host)
    return{
        "message": f"Playbook {request.playbook_name} execution started"
    }

@router.post("/setup_challenge")
def setup_vm(ansible_service: AnsibleServiceDep):
    """Buat VM baru dan setup challenge di VM tersebut"""
    # Clone
    # Gimana cara dapet ip dari vm yang udah dibuat?
    logger.info("Cloning VM")
    vm = ansible_service.run_playbook("clone_vm.yml", "localhost", {
        "vmid": 100,
        "vm_name": "test-vm",
        "vm_template": "cloud-init"
    })

    # Setup challenge di VM
    #TODO: implementasi setup challenge dengan ansible playbook
    return{
        "message": "VM creation playbook execution started"
    }

