"""
AWSProvider — implementasi InfraProvider untuk AWS EC2.

Strategi: **boto3 untuk control-plane** (launch/terminate EC2, jaringan) +
**Ansible untuk in-VM** (reuse setup_challenge.yml / post_challenge.yml yang
SAMA seperti Proxmox, lewat koneksi direct-SSH ke public IP EC2).

Asumsi/penyederhanaan awal:
- Security group (AWS_SECURITY_GROUP_ID) sudah dibuat & mengizinkan porta 80
  (challenge via nginx+auth) dan 22 (Ansible). Di-attach saat launch, jadi
  configure_access cukup mengembalikan URL.
- Instance memperoleh public IP otomatis (tanpa EIP), disimpan di Deployment.vm_ip.
- Instance-id (string) disimpan di Deployment.vm_name (Deployment.vm_id tetap None
  untuk AWS; generalisasi vm_id->instance_ref menyusul).
- Image registry harus terjangkau dari EC2 (ECR / registry publik) — lihat todolist.
"""
from __future__ import annotations

from time import sleep
from typing import Optional, TYPE_CHECKING

from config.settings import Settings
from core.logging import logger
from core.exceptions import VMCreationError
from services.ansible_service import AnsibleService
from services.providers.base import (
    InfraProvider,
    ReservedInstance,
    InstanceHandle,
    AccessInfo,
)

if TYPE_CHECKING:
    from models import Challenge, Deployment, Level


class AWSProvider(InfraProvider):
    """Penyedia infrastruktur berbasis AWS EC2."""

    name = "aws"

    def __init__(self, settings: Settings):
        self.settings = settings
        # Lazy import agar package providers tetap bisa di-import tanpa boto3.
        import boto3
        self.ec2 = boto3.client(
            "ec2",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
        )
        self.ansible_service = AnsibleService(settings)

    # ── Reservation & handle ────────────────────────────────────────────────

    def reserve(self, *, level_id: int, team: str) -> ReservedInstance:
        # AWS tidak punya VMID untuk di-reserve sebelum instance dibuat; identitas
        # (instance-id + public IP) baru diketahui setelah create/launch.
        return ReservedInstance()

    def handle_from_deployment(self, deployment: "Deployment") -> InstanceHandle:
        # instance-id disimpan di vm_name, public IP di vm_ip.
        return InstanceHandle(
            ref=deployment.vm_name or "",
            ansible_host=deployment.vm_ip or "",
            name=deployment.vm_name,
        )

    # ── Lifecycle (boto3) ───────────────────────────────────────────────────

    def create_instance(
        self, *, challenge: "Challenge", deployment: "Deployment", level: Optional["Level"]
    ) -> InstanceHandle:
        if not self.settings.AWS_AMI_ID:
            raise VMCreationError("AWS_AMI_ID belum diset")

        run_kwargs = {
            "ImageId":      self.settings.AWS_AMI_ID,
            "InstanceType": self.settings.AWS_INSTANCE_TYPE,
            "MinCount":     1,
            "MaxCount":     1,
            "TagSpecifications": [{
                "ResourceType": "instance",
                "Tags": [
                    {"Key": "Name",             "Value": f"ctf-{challenge.team}-{challenge.level_id}"},
                    {"Key": "ctf_challenge_id", "Value": str(challenge.id)},
                    {"Key": "ctf_team",         "Value": challenge.team},
                ],
            }],
        }
        if self.settings.AWS_KEY_PAIR_NAME:
            run_kwargs["KeyName"] = self.settings.AWS_KEY_PAIR_NAME
        if self.settings.AWS_SUBNET_ID:
            run_kwargs["SubnetId"] = self.settings.AWS_SUBNET_ID
        if self.settings.AWS_SECURITY_GROUP_ID:
            run_kwargs["SecurityGroupIds"] = [self.settings.AWS_SECURITY_GROUP_ID]

        resp = self.ec2.run_instances(**run_kwargs)
        instance_id = resp["Instances"][0]["InstanceId"]
        logger.info(f"[aws] EC2 launched: {instance_id}")
        # public IP belum ada sampai instance running; diisi di wait_ready().
        return InstanceHandle(ref=instance_id, ansible_host="", name=instance_id)

    def wait_ready(self, handle: InstanceHandle) -> None:
        logger.info(f"[aws] Waiting for instance {handle.ref} to run...")
        self.ec2.get_waiter("instance_running").wait(InstanceIds=[handle.ref])

        desc = self.ec2.describe_instances(InstanceIds=[handle.ref])
        inst = desc["Reservations"][0]["Instances"][0]
        public_ip = inst.get("PublicIpAddress")
        if not public_ip:
            raise VMCreationError(f"EC2 {handle.ref} tidak memperoleh public IP")
        handle.ansible_host = public_ip
        logger.info(f"[aws] Instance {handle.ref} public IP: {public_ip}")

        # Tunggu status checks OK supaya SSH (untuk Ansible) sudah siap.
        logger.info(f"[aws] Waiting for status checks on {handle.ref}...")
        self.ec2.get_waiter("instance_status_ok").wait(InstanceIds=[handle.ref])
        # Jeda kecil agar sshd benar-benar menerima koneksi.
        sleep(5)

    def configure_access(self, handle: InstanceHandle) -> AccessInfo:
        # Security group (di-attach saat launch) sudah mengizinkan porta 80.
        # Challenge dilayani nginx+auth pada port 80 via public IP.
        return AccessInfo(url=f"http://{handle.ansible_host}")

    # ── In-VM setup (Ansible, reuse playbook yang sama via direct SSH) ───────

    def setup_challenge(
        self, handle: InstanceHandle, *, challenge: "Challenge", level: Optional["Level"]
    ) -> None:
        from passlib.hash import apr_md5_crypt
        vm_password_hash = apr_md5_crypt.hash(challenge.vm_password) if challenge.vm_password else ""

        image_tag = level.template_url if level and level.template_url else f"level-{challenge.level_id}"
        self.ansible_service.run_playbook(
            playbook="setup_challenge.yml",
            hosts=handle.ansible_host,
            direct=True,
            ssh_user=self.settings.AWS_SSH_USER,
            ssh_key=self.settings.AWS_SSH_KEY_PATH,
            extra_vars={
                "challenge_id":      challenge.id,
                "team":              challenge.team,
                "flag":              challenge.flag,
                "vmid":              0,  # tidak relevan untuk AWS (dir pakai image_tag)
                "image_tag":         image_tag,
                "registry_host":     self.settings.REGISTRY_HOST,
                "source_url":        level.source_url if level else "",
                "compose_content":   level.compose_content if level else "",
                "vm_user":           challenge.team,
                "vm_password_hash":  vm_password_hash,
            },
        )

    def cleanup_challenge(self, handle: InstanceHandle, *, team: str) -> None:
        # Tidak perlu: destroy_instance menghapus seluruh instance.
        return

    # ── Teardown (boto3) ─────────────────────────────────────────────────────

    def remove_access(self, handle: InstanceHandle) -> None:
        # Security group bersifat shared & persisten; tidak ada EIP. No-op.
        return

    def destroy_instance(self, handle: InstanceHandle) -> None:
        if handle.ref:
            self.ec2.terminate_instances(InstanceIds=[handle.ref])
            logger.info(f"[aws] EC2 terminated: {handle.ref}")
