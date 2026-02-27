from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List

class AnsiblePlaybookParams(BaseModel):
    """
    Parameters model for running an Ansible Playbook
    """
    host: str = Field(..., description="IP Address atau Hostname target")
    playbook_name: str = Field(..., description="Nama file playbook (contoh: setup_web.yml)")
    challenge_id: int = Field(..., description="Challenge ID")
    challenge_name: str = Field(..., description="Nama Challenge")
    vulnhub_machine: Optional[str] = Field(None, description="Vulhub machine name")
    vm_id: Optional[int] = Field(None, description="ID VM (jika sudah diketahui)")

class AnsiblePlaybookReturn(BaseModel):
    """
    Result of Ansible Playbook execution
    """
    success: bool
    status: str = Field(..., description="Status runner (successful, failed, error)")
    rc: int = Field(..., description="Return Code")
    events: List[Dict[str, Any]] = Field(default_factory=list, description="List event/log penting")
    stats: Dict[str, Any] = Field(default_factory=dict, description="Statistik (ok, changed, failed)")
    stdout: Optional[str] = Field(None, description="Raw stdout output")