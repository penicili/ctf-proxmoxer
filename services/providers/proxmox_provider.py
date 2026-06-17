"""
ProxmoxProvider — implementasi InfraProvider untuk Proxmox VE.

Membungkus ProxmoxService (lifecycle VM) dan AnsibleService (port forwarding di
host PVE + setup challenge di dalam VM). Perilaku dipertahankan persis seperti
implementasi sebelumnya di challenge_service; hanya dipindahkan ke balik
interface agar provider lain dapat ditambahkan tanpa mengubah orkestrasi.
"""
from __future__ import annotations

from time import sleep
from typing import Optional, TYPE_CHECKING

from config.settings import Settings
from core.logging import logger
from core.exceptions import VMCreationError
from services.proxmox_service import ProxmoxService
from services.ansible_service import AnsibleService
from services.providers.base import (
    InfraProvider,
    ReservedInstance,
    InstanceHandle,
    AccessInfo,
)

if TYPE_CHECKING:
    from models import Challenge, Deployment, Level


class ProxmoxProvider(InfraProvider):
    """Penyedia infrastruktur berbasis Proxmox VE."""

    name = "proxmox"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.proxmox_service = ProxmoxService(settings)
        self.ansible_service = AnsibleService(settings)

    # ── Reservation & handle ────────────────────────────────────────────────

    def reserve(self, *, level_id: int, team: str) -> ReservedInstance:
        vmid = self.proxmox_service._get_next_vmid()
        return ReservedInstance(
            vm_id=vmid,
            vm_ip=f"{self.settings.VM_SUBNET}.{vmid}",
        )

    def handle_from_deployment(self, deployment: "Deployment") -> InstanceHandle:
        return InstanceHandle(
            ref=str(deployment.vm_id) if deployment.vm_id is not None else "",
            ansible_host=deployment.vm_ip or "",
            name=deployment.vm_name,
        )

    # ── Lifecycle ───────────────────────────────────────────────────────────

    def create_instance(
        self, *, challenge: "Challenge", deployment: "Deployment", level: Optional["Level"]
    ) -> InstanceHandle:
        vm_result = self.proxmox_service.create_vm(
            level_id=challenge.level_id,
            team=challenge.team,
            time_limit=self.settings.DEFAULT_CHALLENGE_DURATION,
            config={"template_vmid": self.settings.TEMPLATE_VMID},
            vmid=deployment.vm_id,
        )
        name = vm_result.info.name if vm_result.info else None
        return InstanceHandle(
            ref=str(vm_result.vmid),
            ansible_host=deployment.vm_ip or f"{self.settings.VM_SUBNET}.{vm_result.vmid}",
            name=name,
        )

    def wait_ready(self, handle: InstanceHandle) -> None:
        proxmox = self.proxmox_service._ensure_connected()
        vmid = int(handle.ref)
        max_wait = 180
        interval = 5
        elapsed = 0
        logger.info(f"[proxmox] Waiting for QEMU guest agent on VMID {vmid}...")
        while elapsed < max_wait:
            try:
                proxmox.nodes(self.settings.PROXMOX_NODE).qemu(vmid).agent.ping.post()
                logger.info(f"[proxmox] Guest agent ready on VMID {vmid} after {elapsed}s")
                return
            except Exception:
                pass
            sleep(interval)
            elapsed += interval
        raise VMCreationError(f"Guest agent on VMID {vmid} not ready after {max_wait}s")

    def configure_access(self, handle: InstanceHandle) -> AccessInfo:
        vmid = int(handle.ref)
        ssh_port = self.settings.SSH_PORT_BASE + vmid
        http_port = self.settings.HTTP_PORT_BASE + vmid

        self.ansible_service.run_playbook(
            playbook="setup_port_forward.yml",
            hosts=self.settings.PROXMOX_HOST,
            is_pve=True,
            extra_vars={
                "vm_ip":         handle.ansible_host,
                "ssh_port":      ssh_port,
                "http_port":     http_port,
                "pve_public_ip": self.settings.PVE_PUBLIC_IP,
            },
        )
        logger.info(f"[proxmox] Port forwarding set: SSH={ssh_port}, HTTP={http_port}")
        return AccessInfo(url=f"http://{self.settings.PVE_PUBLIC_IP}:{http_port}")

    def setup_challenge(
        self, handle: InstanceHandle, *, challenge: "Challenge", level: Optional["Level"]
    ) -> None:
        # Hash Apache-MD5 untuk nginx .htpasswd (autentikasi per-tim).
        from passlib.hash import apr_md5_crypt
        vm_password_hash = apr_md5_crypt.hash(challenge.vm_password) if challenge.vm_password else ""

        image_tag = level.template_url if level and level.template_url else f"level-{challenge.level_id}"
        self.ansible_service.run_playbook(
            playbook="setup_challenge.yml",
            hosts=handle.ansible_host,
            extra_vars={
                "challenge_id":      challenge.id,
                "team":              challenge.team,
                "flag":              challenge.flag,
                "vmid":              int(handle.ref),
                "image_tag":         image_tag,
                "registry_host":     self.settings.REGISTRY_HOST,
                "source_url":        level.source_url if level else "",
                "compose_content":   level.compose_content if level else "",
                "vm_user":           challenge.team,
                "vm_password_hash":  vm_password_hash,
            },
        )

    def cleanup_challenge(self, handle: InstanceHandle, *, team: str) -> None:
        self.ansible_service.run_playbook(
            playbook="post_challenge.yml",
            hosts=handle.ansible_host,
            extra_vars={
                "vmid": int(handle.ref),
                "team": team,
            },
        )

    def remove_access(self, handle: InstanceHandle) -> None:
        vmid = int(handle.ref)
        ssh_port = self.settings.SSH_PORT_BASE + vmid
        http_port = self.settings.HTTP_PORT_BASE + vmid
        self.ansible_service.run_playbook(
            playbook="remove_port_forward.yml",
            hosts=self.settings.PROXMOX_HOST,
            is_pve=True,
            extra_vars={
                "vm_ip":         handle.ansible_host,
                "ssh_port":      ssh_port,
                "http_port":     http_port,
                "pve_public_ip": self.settings.PVE_PUBLIC_IP,
            },
        )

    def destroy_instance(self, handle: InstanceHandle) -> None:
        # Perilaku saat ini: VM di-stop (bukan dihapus) pada terminasi.
        self.proxmox_service.stop_vm(int(handle.ref))
