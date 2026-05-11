import secrets
import requests
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from core.database import SessionLocal
from core.logging import logger
from core.exceptions import VMCreationError, ResourceNotFoundError, AnsiblePlaybookError
from config.settings import Settings
from models import Challenge, Deployment, Level
from models.Deployment import DeploymentStatus
from models.Level import PrepareStatusEnum
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

        # ── Step 4: Setup challenge di VM via Ansible (docker run saja, image sudah ada di template)
        ansible_service.run_playbook(
            playbook="setup_challenge.yml",
            hosts=deployment.vm_ip,
            extra_vars={
                "challenge_id": challenge.id,
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

        # ── Step 6: Buat challenge + flag di CTFd via API ───────────────
        access_http = f"http://{settings.PVE_PUBLIC_IP}:{http_port}"
        ctfd_id = _finalize_ctfd_challenge(settings, challenge, level, access_http)
        if ctfd_id:
            logger.info(f"[deploy_bg] CTFd challenge finalized: ctfd_id={ctfd_id}")
        else:
            logger.warning(f"[deploy_bg] CTFd finalize skipped or failed for challenge {challenge_id}")

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


def prepare_level_template_bg(level_id: int) -> None:
    """
    Background task: clone base template → install challenge → convert ke template.
    Setelah selesai, level.template_url akan di-update ke VMID template baru.
    """
    db: Session = SessionLocal()
    new_vmid = None
    try:
        from config.settings import settings
        proxmox_service = ProxmoxService(settings)
        ansible_service = AnsibleService(settings)

        level: Optional[Level] = db.query(Level).filter(Level.id == level_id).first()
        if not level:
            logger.error(f"[prepare_tpl] Level {level_id} not found")
            return

        if not level.source_url:
            logger.error(f"[prepare_tpl] Level {level_id} has no source_url")
            return

        level.prepare_status = PrepareStatusEnum.PREPARING
        level.prepare_error = None
        db.commit()
        logger.info(f"[prepare_tpl] Preparing template for level '{level.name}' (source: {level.source_url})")

        # ── Step 1: Clone base template (spec tinggi untuk build) ────────────
        vm_config = {
            "template_vmid": settings.TEMPLATE_VMID,
            "memory": 2048,
            "cores": 2,
            "cpu_type": "host",
        }
        vm_result = proxmox_service.create_vm(
            level_id=level_id,
            team="template",
            time_limit=0,
            config=vm_config,
        )
        new_vmid = vm_result.vmid
        vm_ip = f"{settings.VM_SUBNET}.{new_vmid}"
        logger.info(f"[prepare_tpl] VM cloned: vmid={new_vmid}, ip={vm_ip}")

        # ── Step 2: Wait for boot ────────────────────────────────────────────
        import time
        logger.info("[prepare_tpl] Waiting 30s for VM boot + cloud-init...")
        time.sleep(30)

        # ── Step 3: Run prepare_challenge.yml (git clone + docker build) ─────
        ansible_service.run_playbook(
            playbook="prepare_challenge.yml",
            hosts=vm_ip,
            extra_vars={
                "source_url": level.source_url,
            },
        )
        logger.info(f"[prepare_tpl] Challenge installed in VM {new_vmid}")

        # ── Step 4: Shutdown VM ──────────────────────────────────────────────
        proxmox_service.shutdown_vm(new_vmid)
        logger.info(f"[prepare_tpl] VM {new_vmid} stopped")

        # ── Step 5: Convert to template ──────────────────────────────────────
        proxmox_service.convert_to_template(new_vmid)
        logger.info(f"[prepare_tpl] VM {new_vmid} converted to template")

        # ── Step 6: Update level ─────────────────────────────────────────────
        level.template_url = str(new_vmid)
        level.prepare_status = PrepareStatusEnum.READY
        level.prepare_error = None
        db.commit()
        logger.info(f"[prepare_tpl] Level '{level.name}' template_url updated to {new_vmid}")

    except Exception as e:
        logger.exception(f"[prepare_tpl] Failed to prepare template for level {level_id}: {e}")
        try:
            level = db.query(Level).filter(Level.id == level_id).first()
            if level:
                level.prepare_status = PrepareStatusEnum.ERROR
                level.prepare_error = str(e)
                db.commit()
        except Exception:
            pass
        # Cleanup: destroy VM jika sudah dibuat tapi gagal
        if new_vmid:
            try:
                from config.settings import settings
                proxmox_service = ProxmoxService(settings)
                proxmox_service.shutdown_vm(new_vmid)
                proxmox_service.destroy_vm(new_vmid)
                logger.info(f"[prepare_tpl] Cleaned up VM {new_vmid}")
            except Exception:
                pass
    finally:
        db.close()


def _finalize_ctfd_challenge(settings: Settings, challenge: Challenge, level: Level, access_http: Optional[str] = None) -> Optional[int]:
    """
    Buat entri challenge + flag di CTFd via REST API.
    Return ctfd_challenge_id jika berhasil, None jika gagal.
    """
    if not settings.CTFD_API_TOKEN:
        logger.warning("[finalize] CTFD_API_TOKEN not set, skipping CTFd challenge creation")
        return None

    base_url = settings.CTFD_URL.rstrip("/")
    headers = {
        "Authorization": f"Token {settings.CTFD_API_TOKEN}",
        "Content-Type": "application/json",
    }

    # Buat description dengan info akses
    description = level.description or ""
    if access_http:
        description += f"\n\n**Challenge URL:** {access_http}"

    # Step 1: Buat challenge di CTFd
    challenge_payload = {
        "name": f"{level.name} [{challenge.team}]",
        "description": description.strip(),
        "category": level.category,
        "value": level.points,
        "type": "standard",
        "state": "visible",
    }
    logger.info(f"[finalize] Getting challenge id  to CTFd")
    resp = requests.post(f"{base_url}/api/v1/challenges", json=challenge_payload, headers=headers)
    if not resp.ok:
        logger.error(f"[finalize] Failed to create CTFd challenge: {resp.status_code} {resp.text}")
        return None

    ctfd_challenge_id = resp.json()["data"]["id"]
    logger.info(f"[finalize] CTFd challenge created: id={ctfd_challenge_id}")

    # Step 2: Set flag
    flag_payload = {
        "challenge_id": ctfd_challenge_id,
        "type": "static",
        "content": challenge.flag,
        "data": "",
    }
    logger.info(f"[finalize] Creating CTFd challenge: {ctfd_challenge_id} on {base_url}")
    resp = requests.post(f"{base_url}/api/v1/flags", json=flag_payload, headers=headers)
    if not resp.ok:
        logger.error(f"[finalize] Failed to create CTFd flag: {resp.status_code} {resp.text}")
        # Challenge sudah dibuat tapi flag gagal — tetap return ID
        return ctfd_challenge_id

    logger.info(f"[finalize] CTFd flag set for challenge {ctfd_challenge_id}")
    return ctfd_challenge_id


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
