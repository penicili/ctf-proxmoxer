from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List

class AnsiblePlaybookParams(BaseModel):
    """
    Parameters model for running an Ansible Playbook
    """
    host: str = Field(..., description="IP Address atau Hostname target")
    playbook_name: str = Field(..., description="Nama file playbook (contoh: setup_web.yml)")
    user: str = Field(default="root", description="SSH User")
    # Private key opsional, jika tidak ada akan pakai default system/settings
    private_key: Optional[str] = Field(None, description="Isi Private Key (string) jika custom") 
    extra_vars: Dict[str, Any] = Field(default_factory=dict, description="Variabel tambahan untuk playbook")

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