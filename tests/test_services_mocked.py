import pytest
from unittest.mock import MagicMock, patch, ANY
from typing import Dict, Any

from schemas.types.Vm_types import VMResult, VMInfo
from schemas.types.Ansible_types import AnsiblePlaybookRequest, AnsiblePlaybookResult
from schemas.types.Challenge_types import ChallengeResult
from services.proxmox_service import ProxmoxService
from services.ansible_service import AnsibleService
from services.challange_service import ChallengeService
from config.settings import Settings
from models import Challenge, Deployment

# --- Fixtures ---

@pytest.fixture
def mock_settings():
    settings = Settings()
    settings.PROXMOX_HOST = "mock_host"
    settings.PROXMOX_USER = "mock_user"
    settings.PROXMOX_PASSWORD = "mock_password"
    return settings

@pytest.fixture
def mock_proxmox_api():
    """Mocks the 'proxmoxer.ProxmoxAPI' class"""
    with patch("services.proxmox_service.ProxmoxAPI") as mock:
        yield mock

@pytest.fixture
def mock_ansible_runner_run():
    """
    Mocks the 'run' function of ansible_runner imported inside 'services.ansible_service'.
    """
    with patch("services.ansible_service.ansible_runner.run") as mock:
        yield mock

@pytest.fixture
def mock_db_session():
    """Mocks SQLAlchemy Session"""
    session = MagicMock()
    # Mocking add/commit/refresh methods to do nothing or return values
    session.add = MagicMock()
    session.commit = MagicMock()
    session.refresh = MagicMock()
    session.rollback = MagicMock()
    session.flush = MagicMock()
    return session

# --- Tests for ProxmoxService ---

def test_proxmox_create_vm_success(mock_settings, mock_proxmox_api):
    # Setup Service
    service = ProxmoxService(mock_settings)
    
    # Mock ProxmoxAPI instance and methods
    instance = mock_proxmox_api.return_value
    instance.version.get.return_value = {"version": "7.4"}
    
    # Mock list_vms to return empty list so VMID 200 is available
    instance.nodes.return_value.qemu.get.return_value = []
    instance.nodes.return_value.lxc.get.return_value = []
    
    # Mock VM Config Get (get_vm_info)
    # Proxmoxer return dynamic dict, so we mock dictionary behavior
    mock_vm_config = {
        "name": "team-A-1-200",
        "memory": 1024,
        "status": "running"
    }
    instance.nodes.return_value.qemu.return_value.config.get.return_value = mock_vm_config
    
    # Execute
    result = service.create_vm(level_id=1, team="team-A", time_limit=60, config={})
    
    # Assert
    assert isinstance(result, VMResult)
    assert result.status == "success"
    assert result.vmid == 200 # Default starting ID
    assert result.info.name == "team-A-1-200"
    
    # Verify calls
    # Check if create VM (post) was called
    instance.nodes.return_value.qemu.post.assert_called_once()
    # Check if start VM was called
    instance.nodes.return_value.qemu.return_value.status.start.post.assert_called_once()

# --- Tests for AnsibleService ---

def test_ansible_run_playbook_success(mock_settings, mock_ansible_runner_run):
    service = AnsibleService(mock_settings)
    
    # Mock Runner Return Object (Result of runner.run())
    mock_runner_obj = MagicMock()
    mock_runner_obj.status = "successful"
    mock_runner_obj.rc = 0
    mock_runner_obj.stats = {"ok": 1, "changed": 1}
    # Mock stdout attribute correctly as a file-like object
    mock_runner_obj.stdout = MagicMock()
    mock_runner_obj.stdout.read.return_value = "Playbook executed successfully"
    
    # Configure mock return
    mock_ansible_runner_run.return_value = mock_runner_obj
    
    # Request
    req = AnsiblePlaybookRequest(host="192.168.1.50", playbook_name="test.yml")
    
    # Execute
    result = service.run_playbook(req)
    
    # DEBUG INFO
    print(f"\n[DEBUG] Service Result: success={result.success}, status={result.status}, rc={result.rc}")
    print(f"[DEBUG] Mock Object Status: {mock_runner_obj.status}, RC: {mock_runner_obj.rc}")
    
    # Assert
    assert result.success is True
    assert result.status == "successful"
    assert result.rc == 0
    
    # Verify inventory was passed
    mock_ansible_runner_run.assert_called_once()
    call_kwargs = mock_ansible_runner_run.call_args[1]
    assert "inventory" in call_kwargs
    assert "192.168.1.50" in call_kwargs["inventory"]["all"]["hosts"]

# --- Tests for ChallengeService (Integration Logic) ---

def test_create_challenge_workflow(mock_db_session, mock_settings):
    # Mock Dependencies
    mock_proxmox_service = MagicMock(spec=ProxmoxService)
    mock_ansible_service = MagicMock(spec=AnsibleService)
    
    # Setup DB Side Effect to simulate ID assignment
    def db_add_side_effect(obj):
        if isinstance(obj, Challenge):
            obj.id = 101 # Simulate DB ID
        elif isinstance(obj, Deployment):
            obj.id = 505
            
    mock_db_session.add.side_effect = db_add_side_effect
    
    # Setup Service
    service = ChallengeService(mock_db_session, mock_proxmox_service, mock_ansible_service, mock_settings)
    
    # 1. Mock VM Creation Success
    vm_info = VMInfo(name="team-A-1-200", status="running", memory=1024)
    vm_result = VMResult(status="success", vmid=200, info=vm_info)
    mock_proxmox_service.create_vm.return_value = vm_result
    
    # 2. Mock Ansible Success
    ansible_res = AnsiblePlaybookResult(success=True, status="successful", rc=0, stats={})
    mock_ansible_service.run_playbook.return_value = ansible_res
    
    # Execute
    result = service.create_challenge(level_id=1, team_name="Team-Alpha")
    
    # Assert
    assert isinstance(result, ChallengeResult)
    assert result.success is True
    assert result.challenge_id == 101 # Verify ID from side_effect
    assert result.vm_info == vm_result
    assert "CTF{" in result.flag
    
    # Verify Workflow
    # 1. Proxmox create_vm called
    mock_proxmox_service.create_vm.assert_called_once_with(
        level_id=1, team="Team-Alpha", time_limit=60, config={}
    )
    
    # 2. Ansible run_playbook called
    mock_ansible_service.run_playbook.assert_called_once()
    # Check if flag was passed to extra_vars
    ansible_call_arg = mock_ansible_service.run_playbook.call_args[0][0] # First arg is request
    assert "challenge_flag" in ansible_call_arg.extra_vars
    # Ensure it uses the VM name from vm_info as host
    assert ansible_call_arg.host == "team-A-1-200" 
    
    # 3. DB interactions
    # Challenge added first, then Deployment
    assert mock_db_session.add.call_count == 2 
    # Verify first add was Challenge, second was Deployment
    first_add_arg = mock_db_session.add.call_args_list[0][0][0]
    second_add_arg = mock_db_session.add.call_args_list[1][0][0]
    
    assert isinstance(first_add_arg, Challenge)
    assert isinstance(second_add_arg, Deployment)
    
    assert mock_db_session.commit.call_count == 1 # Commit happens once at the end (or flush+commit)