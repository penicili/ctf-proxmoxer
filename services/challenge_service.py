import secrets
import requests
from datetime import datetime
from typing import Optional
from time import sleep

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
from services.providers import get_provider


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
        provider = get_provider(settings)

        challenge: Optional[Challenge] = db.query(Challenge).filter(Challenge.id == challenge_id).first()
        if not challenge:
            logger.error(f"[deploy_bg] Challenge {challenge_id} not found")
            return

        deployment: Optional[Deployment] = challenge.deployment
        if not deployment:
            logger.error(f"[deploy_bg] Deployment for challenge {challenge_id} not found")
            return

        level: Optional[Level] = challenge.level

        # ── Step 1: CREATING ─────────────────────────────────────────────────
        # Identifier (mis. VMID) sudah di-reserve di router sebelum bg task
        # di-queue, tersimpan di deployment record.
        deployment.status = DeploymentStatus.CREATING
        db.commit()
        logger.info(
            f"[deploy_bg] Deploying challenge {challenge_id} for team '{challenge.team}' "
            f"via {provider.name} (ref={deployment.vm_id})"
        )

        # ── Step 2: Buat instance (provider-specific) ────────────────────────
        handle = provider.create_instance(challenge=challenge, deployment=deployment, level=level)
        deployment.vm_name = handle.name
        db.commit()
        logger.info(f"[deploy_bg] Instance created: ref={handle.ref}, host={handle.ansible_host}")

        # ── Step 3: Tunggu instance siap ─────────────────────────────────────
        provider.wait_ready(handle)
        # Persist alamat instance (utk AWS, public IP baru diketahui setelah running;
        # utk Proxmox nilainya sama dengan yang di-reserve).
        deployment.vm_ip = handle.ansible_host
        db.commit()

        # ── Step 4: Atur akses jaringan peserta ──────────────────────────────
        access = provider.configure_access(handle)
        logger.info(f"[deploy_bg] Access configured: {access.url}")

        # ── Step 5: Setup challenge di dalam instance (compose up + auth) ─────
        provider.setup_challenge(handle, challenge=challenge, level=level)
        logger.info(f"[deploy_bg] setup_challenge done for challenge {challenge_id}")

        # ── Step 6: RUNNING ──────────────────────────────────────────────────
        deployment.status     = DeploymentStatus.RUNNING
        deployment.started_at = datetime.utcnow()
        db.commit()
        logger.info(f"[deploy_bg] Challenge {challenge_id} is now RUNNING")

        # ── Step 7: Buat challenge + flag di CTFd via API ────────────────────
        ctfd_id = _finalize_ctfd_challenge(settings, challenge, level, access.url)
        if ctfd_id:
            challenge.ctfd_id = ctfd_id
            db.commit()
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
        provider = get_provider(settings)

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
        logger.info(f"[terminate_bg] Terminating challenge {challenge_id} via {deployment.provider}")

        handle = provider.handle_from_deployment(deployment)

        # ── Step 2: Pembersihan di dalam instance (opsional) ─────────────────
        if handle.ansible_host:
            try:
                provider.cleanup_challenge(handle, team=challenge.team)
            except Exception as e:
                logger.warning(f"[terminate_bg] cleanup_challenge failed (non-fatal): {e}")

        # ── Step 2b: Cabut akses jaringan ────────────────────────────────────
        if handle.ref:
            try:
                provider.remove_access(handle)
                logger.info(f"[terminate_bg] Access removed for instance {handle.ref}")
            except Exception as e:
                logger.warning(f"[terminate_bg] remove_access failed (non-fatal): {e}")

        # ── Step 3: Hentikan/hapus instance ──────────────────────────────────
        if handle.ref:
            try:
                provider.destroy_instance(handle)
                deployment.stopped_at = datetime.utcnow()
                db.commit()
                logger.info(f"[terminate_bg] Instance {handle.ref} destroyed")
            except Exception as e:
                logger.warning(f"[terminate_bg] destroy_instance failed (non-fatal): {e}")

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
    Background task: build Docker image challenge di CI runner, push ke registry.
    Setelah selesai, level.template_url di-update ke image_tag di registry.
    """
    db: Session = SessionLocal()
    try:
        from config.settings import settings
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

        image_tag = f"level-{level_id}"
        logger.info(f"[prepare_tpl] Building image '{image_tag}' for level '{level.name}'")

        # ── Run prepare_challenge.yml di CI runner ───────────────────────────
        ansible_service.run_playbook(
            playbook="prepare_challenge.yml",
            hosts=settings.CI_RUNNER_IP,
            extra_vars={
                "source_url":    level.source_url,
                "image_tag":     image_tag,
                "registry_host": settings.REGISTRY_HOST,
            },
        )
        logger.info(f"[prepare_tpl] Image pushed: {settings.REGISTRY_HOST}/{image_tag}:latest")

        # ── Ambil docker-compose.yml yang di-fetch playbook ──────────────────
        # Disimpan ke DB agar deploy tidak perlu clone repo dari GitHub lagi.
        compose_path = f"/tmp/ctf-compose/{image_tag}.yml"
        try:
            with open(compose_path, "r", encoding="utf-8") as f:
                level.compose_content = f.read()
            logger.info(f"[prepare_tpl] docker-compose.yml tersimpan ke DB ({len(level.compose_content)} bytes)")
        except FileNotFoundError:
            level.compose_content = None
            logger.warning(f"[prepare_tpl] docker-compose.yml tidak ditemukan di {compose_path}; deploy akan fallback ke git clone")

        # ── Update level ─────────────────────────────────────────────────────
        level.template_url = image_tag
        level.prepare_status = PrepareStatusEnum.READY
        level.prepare_error = None
        db.commit()
        logger.info(f"[prepare_tpl] Level '{level.name}' ready, image_tag={image_tag}")

    except Exception as e:
        logger.exception(f"[prepare_tpl] Failed to prepare level {level_id}: {e}")
        try:
            level = db.query(Level).filter(Level.id == level_id).first()
            if level:
                level.prepare_status = PrepareStatusEnum.ERROR
                level.prepare_error = str(e)
                db.commit()
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

    # Step 1: Buat challenge di CTFd dengan custom challenge type
    challenge_payload = {
        "name": f"{level.name} [{challenge.team}]",
        "description": description.strip(),
        "category": level.category,
        "value": level.initial_points,
        "type": "team_isolated_dynamic",
        "state": "visible",
        # Scoring params untuk cross-sibling decay
        "level_id": level.id,
        "assigned_team": challenge.team,
        "initial": level.initial_points,
        "minimum": level.minimum_points,
        "decay": level.decay,
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
