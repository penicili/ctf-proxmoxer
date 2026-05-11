from fastapi import APIRouter

from api.dependencies import AnsibleServiceDep

router = APIRouter(
    prefix="/playbooks",
    tags=["Ansible Playbooks Management"]
)


@router.get("/list")
def list_playbooks(ansible_service: AnsibleServiceDep):
    """List available Ansible playbooks."""
    try:
        playbooks = ansible_service.get_playbooks()
        return {"total": len(playbooks), "playbooks": playbooks}
    except Exception as e:
        return {"total": 0, "playbooks": [], "error": str(e)}
