import secrets
from fastapi import APIRouter, BackgroundTasks, HTTPException
from sqlalchemy.exc import IntegrityError
from typing import Optional

from api.dependencies import DbSessionDep
from models import Challenge, Deployment, Level
from models.Deployment import DeploymentStatus
from services.proxmox_service import ProxmoxService
from schemas.requests.challenges_requests import CreateChallengeRequest
from schemas.responses.challenges_responses import (
    ChallengeResponse,
    ChallengeListResponse,
    CreateChallengeResponse,
    CreateChallengeResult,
)
from services.challenge_service import ChallengeService, deploy_challenge_bg, terminate_challenge_bg
from config.settings import settings
from core.logging import logger

router = APIRouter(
    prefix="/challenges",
    tags=["Challenges"]
)


def _build_response(challenge: Challenge) -> ChallengeResponse:
    """Susun ChallengeResponse dari Challenge + relasi Deployment + Level."""
    dep: Optional[Deployment] = challenge.deployment

    # Build access info jika VM sudah running
    access_ssh = None
    access_http = None
    if dep and dep.vm_id and dep.status == DeploymentStatus.RUNNING:
        ssh_port = settings.SSH_PORT_BASE + dep.vm_id
        http_port = settings.HTTP_PORT_BASE + dep.vm_id
        access_ssh = f"ssh user@{settings.PVE_PUBLIC_IP} -p {ssh_port}"
        access_http = f"http://{settings.PVE_PUBLIC_IP}:{http_port}"

    is_running = dep and dep.status == DeploymentStatus.RUNNING

    return ChallengeResponse(
        id=challenge.id,
        level_id=challenge.level_id,
        level_name=challenge.level.name if challenge.level else None,
        team=challenge.team,
        flag=challenge.flag,
        is_active=challenge.is_active,
        created_at=challenge.created_at,
        updated_at=challenge.updated_at,
        ctfd_id=challenge.ctfd_id,
        deployment_status=dep.status.value if dep else None,
        vm_id=dep.vm_id if dep else None,
        vm_name=dep.vm_name if dep else None,
        vm_ip=dep.vm_ip if dep else None,
        error_message=dep.error_message if dep else None,
        started_at=dep.started_at if dep else None,
        terminated_at=dep.terminated_at if dep else None,
        access_ssh=access_ssh,
        access_http=access_http,
        vm_username=challenge.team if is_running else None,
        vm_password=challenge.vm_password if is_running else None,
    )


@router.get("", response_model=ChallengeListResponse)
def list_challenges(
    db: DbSessionDep,
    status: Optional[str] = None,
    team: Optional[str] = None,
):
    query = db.query(Challenge)
    if team:
        query = query.filter(Challenge.team == team)
    if status:
        query = (
            query
            .join(Challenge.deployment)
            .filter(Deployment.status == status)
        )
    challenges = query.order_by(Challenge.id.desc()).all()
    return ChallengeListResponse(
        total=len(challenges),
        challenges=[_build_response(c) for c in challenges],
    )


def _has_active_deployment(db, level_id: int, team_name: str) -> bool:
    """
    Cek apakah tim sudah punya challenge aktif untuk level ini.
    Aktif = is_active=True DAN deployment statusnya bukan TERMINATED/ERROR.
    """
    existing = (
        db.query(Challenge)
        .join(Challenge.deployment)
        .filter(
            Challenge.level_id == level_id,
            Challenge.team == team_name,
            Challenge.is_active == True,
            Deployment.status.notin_([
                DeploymentStatus.TERMINATED,
                DeploymentStatus.ERROR,
            ])
        )
        .first()
    )
    return existing is not None


@router.post("", response_model=CreateChallengeResponse, status_code=202)
def create_challenge(
    db: DbSessionDep,
    request: CreateChallengeRequest,
    background_tasks: BackgroundTasks,
):
    # Validasi level
    level = db.query(Level).filter(Level.id == request.level_id, Level.is_active == True).first()
    if not level:
        raise HTTPException(status_code=404, detail="Level not found or inactive")

    if level.prepare_status.value != "ready":
        raise HTTPException(status_code=400, detail=f"Level is not ready (status: {level.prepare_status.value}). Run prepare first.")

    svc            = ChallengeService(db, None, None, settings)  # type: ignore[arg-type]
    proxmox_svc    = ProxmoxService(settings)
    results: list[CreateChallengeResult] = []
    deployed_count = 0
    skipped_count  = 0

    for team_name in request.team_names:
        # Constraint: satu deployment aktif per (level, team)
        if _has_active_deployment(db, request.level_id, team_name):
            results.append(CreateChallengeResult(
                team=team_name,
                challenge_id=0,
                skipped=True,
                skip_reason=f"Team '{team_name}' sudah memiliki deployment aktif untuk level ini",
            ))
            skipped_count += 1
            logger.info(f"Skipping team '{team_name}': active deployment already exists for level {request.level_id}")
            continue

        # Assign VMID di sini (sequential, satu per satu) sebelum bg task di-queue.
        # Ini mencegah race condition: bg task tidak perlu cari VMID sendiri,
        # tinggal pakai VMID yang sudah di-reserve ke DB.
        try:
            vmid = proxmox_svc._get_next_vmid()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Tidak bisa assign VMID: {e}")

        flag        = svc.generate_flag()
        vm_password = secrets.token_urlsafe(12)
        try:
            with db.begin_nested():
                challenge = Challenge(
                    level_id=request.level_id,
                    team=team_name,
                    flag=flag,
                    vm_password=vm_password,
                    is_active=True,
                )
                db.add(challenge)
                db.flush()

                deployment = Deployment(
                    challenge_id=challenge.id,
                    status=DeploymentStatus.PENDING,
                    vm_id=vmid,                                          # reserve VMID sekarang
                    vm_ip=f"{settings.VM_SUBNET}.{vmid}",               # IP deterministik
                )
                db.add(deployment)
                db.flush()
            db.commit()
            db.refresh(challenge)
        except IntegrityError:
            results.append(CreateChallengeResult(
                team=team_name,
                challenge_id=0,
                skipped=True,
                skip_reason=f"Team '{team_name}' sudah memiliki deployment aktif (concurrent conflict)",
            ))
            skipped_count += 1
            logger.warning(f"Concurrent conflict for team '{team_name}' level {request.level_id}, skipping")
            continue

        logger.info(f"Challenge {challenge.id} created for team '{team_name}', VMID={vmid} reserved, queuing deployment")
        background_tasks.add_task(deploy_challenge_bg, challenge.id)

        results.append(CreateChallengeResult(
            team=team_name,
            challenge_id=challenge.id,
            flag=flag,
            skipped=False,
        ))
        deployed_count += 1

    if deployed_count == 0 and skipped_count > 0:
        # Semua di-skip — return 409
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Semua tim sudah memiliki deployment aktif untuk level ini",
                "results": [r.model_dump() for r in results],
            }
        )

    total = len(request.team_names)
    return CreateChallengeResponse(
        success=True,
        message=f"Deployment dimulai untuk {deployed_count}/{total} tim. {skipped_count} tim di-skip (sudah aktif).",
        results=results,
        deployed=deployed_count,
        skipped=skipped_count,
    )


@router.get("/{challenge_id}", response_model=ChallengeResponse)
def get_challenge(db: DbSessionDep, challenge_id: int):
    challenge = db.query(Challenge).filter(Challenge.id == challenge_id).first()
    if not challenge:
        raise HTTPException(status_code=404, detail="Challenge not found")
    return _build_response(challenge)


@router.delete("/{challenge_id}")
def terminate_challenge(
    db: DbSessionDep,
    challenge_id: int,
    background_tasks: BackgroundTasks,
):
    challenge = db.query(Challenge).filter(Challenge.id == challenge_id).first()
    if not challenge:
        raise HTTPException(status_code=404, detail="Challenge not found")

    dep = challenge.deployment
    if dep and dep.status in (DeploymentStatus.TERMINATED, DeploymentStatus.TERMINATING):
        raise HTTPException(status_code=400, detail=f"Challenge is already {dep.status.value}")

    background_tasks.add_task(terminate_challenge_bg, challenge.id)
    return {"message": "Challenge termination started"}
