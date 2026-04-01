import secrets
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from core.database import SessionLocal
from core.logging import logger
from core.exceptions import VMCreationError, ResourceNotFoundError, AnsiblePlaybookError
from config.settings import Settings
from models import Challenge, Deployment, Level
from models.Deployment import DeploymentStatus
from services.proxmox_service import ProxmoxService
from services.ansible_service import AnsibleService


class ChallengeService:
    """
    Business logic untuk Challenge.
    Mengorkestrasikan ProxmoxService dan AnsibleService.
    """

    def __init__(
        self,
        db: Session,
        proxmox_service: ProxmoxService,
        ansible_service: AnsibleService,
        settings: Settings,
    ):
        self.db = db
        self.proxmox_service = proxmox_service
        self.ansible_service = ansible_service
        self.settings = settings

    def generate_flag(self) -> str:
        """Generate flag unik: CTF{RANDOM...}"""
        charset = self.settings.FLAG_CHARSET
        body = ''.join(secrets.choice(charset) for _ in range(self.settings.FLAG_LENGTH))
        return f"{self.settings.FLAG_PREFIX}{{{body}}}"

    def submit_challenge(self):
        pass  # TODO: untuk future use jika diperlukan


# ── Background Task Functions ────────────────────────────────────────────────
# Fungsi ini berjalan di luar request context, sehingga harus membuat
# DB session sendiri (tidak bisa pakai session dari dependency injection).

def deploy_challenge_bg(challenge_id: int) -> None:
    """
    Background task: clone VM di Proxmox lalu jalankan setup_challenge playbook.
    Dipanggil setelah Challenge dan Deployment record dibuat dengan status PENDING.
    """
    db: Session = SessionLocal()
    try:
        from config.settings import settings
        proxmox_service = ProxmoxService(settings)
        ansible_service = AnsibleService(settings)

        challenge: Optional[Challenge] = db.query(Challenge).filter(Challenge.id == challenge_id).first()
        if not challenge:
            logger.error(f"[deploy_bg] Challenge {challenge_id} not found")
            return

        deployment: Optional[Deployment] = challenge.deployment
        if not deployment:
            logger.error(f"[deploy_bg] Deployment for challenge {challenge_id} not found")
            return

        level: Optional[Level] = challenge.level

        # ── Step 1: CREATING ────────────────────────────────────────────────
        deployment.status = DeploymentStatus.CREATING
        db.commit()
        logger.info(f"[deploy_bg] Deploying challenge {challenge_id} for team '{challenge.team}'")

        # ── Step 2: Clone VM di Proxmox ─────────────────────────────────────
        vm_config = {
            "template_vmid": settings.TEMPLATE_VMID,
        }
        # Level bisa override template VMID (disimpan di template_url sebagai string angka)
        if level and level.template_url:
            try:
                vm_config["template_vmid"] = int(level.template_url)
            except ValueError:
                logger.warning(f"[deploy_bg] Level template_url '{level.template_url}' bukan VMID, pakai default")

        vm_result = proxmox_service.create_vm(
            level_id=challenge.level_id,
            team=challenge.team,
            time_limit=settings.DEFAULT_CHALLENGE_DURATION,
            config=vm_config,
        )

        deployment.vm_id   = vm_result.vmid
        deployment.vm_name = vm_result.info.name if vm_result.info else None
        # IP deterministic dari VMID: e.g. VMID 201 → 10.10.10.201
        deployment.vm_ip = f"{settings.VM_SUBNET}.{vm_result.vmid}"
        db.commit()
        logger.info(f"[deploy_bg] VM created: vmid={vm_result.vmid}, ip={deployment.vm_ip}")

        # ── Wait for VM to boot + cloud-init network ─────────────────────
        import time
        logger.info("[deploy_bg] Waiting 30s for VM boot + cloud-init...")
        time.sleep(30)

        # ── Step 3: Setup port forwarding di PVE host via Ansible ─────────
        ssh_port = settings.SSH_PORT_BASE + vm_result.vmid
        http_port = settings.HTTP_PORT_BASE + vm_result.vmid

        ansible_service.run_playbook(
            playbook="setup_port_forward.yml",
            hosts=settings.PROXMOX_HOST,
            is_pve=True,
            extra_vars={
                "vm_ip":     deployment.vm_ip,
                "ssh_port":  ssh_port,
                "http_port": http_port,
                "pve_public_ip": settings.PVE_PUBLIC_IP,
            },
        )
        logger.info(f"[deploy_bg] Port forwarding set: SSH={ssh_port}, HTTP={http_port}")

        # ── Step 4: Setup challenge di VM via Ansible (SSH via ProxyJump lewat PVE)
        ansible_service.run_playbook(
            playbook="setup_challenge.yml",
            hosts=deployment.vm_ip,
            extra_vars={
                "challenge_id": challenge.id,
                "level_id":     challenge.level_id,
                "team":         challenge.team,
                "flag":         challenge.flag,
                "vmid":         vm_result.vmid,
            },
        )
        logger.info(f"[deploy_bg] Ansible setup_challenge done for challenge {challenge_id}")

        # ── Step 5: RUNNING ─────────────────────────────────────────────────
        deployment.status     = DeploymentStatus.RUNNING
        deployment.started_at = datetime.utcnow()
        db.commit()
        logger.info(f"[deploy_bg] Challenge {challenge_id} is now RUNNING")

    except (VMCreationError, ResourceNotFoundError, AnsiblePlaybookError) as e:
        logger.error(f"[deploy_bg] Challenge {challenge_id} failed: {e}")
        _mark_error(db, challenge_id, str(e))
    except Exception as e:
        logger.exception(f"[deploy_bg] Unexpected error for challenge {challenge_id}: {e}")
        _mark_error(db, challenge_id, str(e))
    finally:
        db.close()


def terminate_challenge_bg(challenge_id: int) -> None:
    """
    Background task: stop dan hapus VM, update status ke TERMINATED.
    """
    db: Session = SessionLocal()
    try:
        from config.settings import settings
        proxmox_service = ProxmoxService(settings)
        ansible_service = AnsibleService(settings)

        challenge: Optional[Challenge] = db.query(Challenge).filter(Challenge.id == challenge_id).first()
        if not challenge:
            logger.error(f"[terminate_bg] Challenge {challenge_id} not found")
            return

        deployment: Optional[Deployment] = challenge.deployment
        if not deployment:
            logger.error(f"[terminate_bg] Deployment for challenge {challenge_id} not found")
            return

        # ── Step 1: TERMINATING ─────────────────────────────────────────────
        deployment.status = DeploymentStatus.TERMINATING
        db.commit()
        logger.info(f"[terminate_bg] Terminating challenge {challenge_id}")

        # ── Step 2: (Opsional) Cleanup playbook ─────────────────────────────
        if deployment.vm_id and deployment.vm_ip:
            try:
                ansible_service.run_playbook(
                    playbook="post_challenge.yml",
                    hosts=deployment.vm_ip,
                    extra_vars={
                        "vmid":  deployment.vm_id,
                        "team":  challenge.team,
                    },
                )
            except Exception as e:
                logger.warning(f"[terminate_bg] post_challenge playbook failed (non-fatal): {e}")

        # ── Step 2b: Remove port forwarding ───────────────────────────────
        if deployment.vm_id and deployment.vm_ip:
            try:
                ssh_port = settings.SSH_PORT_BASE + deployment.vm_id
                http_port = settings.HTTP_PORT_BASE + deployment.vm_id
                ansible_service.run_playbook(
                    playbook="remove_port_forward.yml",
                    hosts=settings.PROXMOX_HOST,
                    is_pve=True,
                    extra_vars={
                        "vm_ip":     deployment.vm_ip,
                        "ssh_port":  ssh_port,
                        "http_port": http_port,
                        "pve_public_ip": settings.PVE_PUBLIC_IP,
                    },
                )
                logger.info(f"[terminate_bg] Port forwarding removed for VM {deployment.vm_id}")
            except Exception as e:
                logger.warning(f"[terminate_bg] remove_port_forward failed (non-fatal): {e}")

        # ── Step 3: Stop VM ─────────────────────────────────────────────────
        if deployment.vm_id:
            try:
                proxmox_service.stop_vm(deployment.vm_id)
                deployment.stopped_at = datetime.utcnow()
                db.commit()
                logger.info(f"[terminate_bg] VM {deployment.vm_id} stopped")
            except Exception as e:
                logger.warning(f"[terminate_bg] stop_vm failed (non-fatal): {e}")

        # ── Step 4: TERMINATED ──────────────────────────────────────────────
        deployment.status        = DeploymentStatus.TERMINATED
        deployment.terminated_at = datetime.utcnow()
        challenge.is_active      = False
        db.commit()
        logger.info(f"[terminate_bg] Challenge {challenge_id} terminated")

    except Exception as e:
        logger.exception(f"[terminate_bg] Unexpected error for challenge {challenge_id}: {e}")
        _mark_error(db, challenge_id, f"Termination failed: {e}")
    finally:
        db.close()


def _mark_error(db: Session, challenge_id: int, message: str) -> None:
    """Helper: set deployment status ke ERROR."""
    try:
        challenge = db.query(Challenge).filter(Challenge.id == challenge_id).first()
        if challenge and challenge.deployment:
            challenge.deployment.status        = DeploymentStatus.ERROR
            challenge.deployment.error_message = message
            db.commit()
    except Exception as e:
        logger.error(f"[_mark_error] Failed to mark error for challenge {challenge_id}: {e}")
