"""
Abstraksi penyedia infrastruktur (InfraProvider).

Mengisolasi bagian yang provider-specific (lifecycle instance + akses jaringan)
dari orkestrasi di ChallengeService. Implementasi konkret: ProxmoxProvider
(saat ini), dan AWSProvider (pengembangan lanjutan).

Bagian yang TIDAK provider-specific (setup challenge di dalam VM lewat
setup_challenge.yml, integrasi CTFd, scoring) tetap reusable; provider hanya
menyediakan "di mana" dan "bagaimana" instance dibuat dan diakses.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from models import Challenge, Deployment, Level


@dataclass
class ReservedInstance:
    """
    Identifier yang di-reserve sebelum instance benar-benar dibuat.
    Dipersist ke record Deployment oleh router agar tidak terjadi double
    allocation pada deploy konkuren.
    """
    vm_id: Optional[int] = None
    vm_ip: Optional[str] = None
    vm_name: Optional[str] = None


@dataclass
class InstanceHandle:
    """
    Referensi ringan ke sebuah instance, dipakai lintas langkah orkestrasi
    (create -> wait -> configure access -> setup -> destroy).
    """
    ref: str                       # id provider-specific (VMID utk proxmox, instance-id utk aws)
    ansible_host: str              # host yang dipakai Ansible untuk menjalankan playbook in-VM
    name: Optional[str] = None


@dataclass
class AccessInfo:
    """Informasi akses peserta ke instance challenge."""
    url: str                       # URL HTTP yang dipakai peserta


class InfraProvider(ABC):
    """
    Kontrak penyedia infrastruktur. ChallengeService memanggil interface ini
    tanpa mengetahui apakah backend-nya Proxmox, AWS, atau lainnya.
    """

    name: str = "base"

    @abstractmethod
    def reserve(self, *, level_id: int, team: str) -> ReservedInstance:
        """Reserve identifier (mis. VMID + IP) sebelum instance dibuat."""

    @abstractmethod
    def handle_from_deployment(self, deployment: "Deployment") -> InstanceHandle:
        """Bangun ulang handle dari record Deployment (dipakai saat terminasi)."""

    @abstractmethod
    def create_instance(
        self, *, challenge: "Challenge", deployment: "Deployment", level: Optional["Level"]
    ) -> InstanceHandle:
        """Buat instance (mis. clone VM / run EC2) dan kembalikan handle-nya."""

    @abstractmethod
    def wait_ready(self, handle: InstanceHandle) -> None:
        """Tunggu instance siap menerima koneksi (guest agent / SSH / status check)."""

    @abstractmethod
    def configure_access(self, handle: InstanceHandle) -> AccessInfo:
        """Atur akses jaringan peserta (port forward / security group) -> URL akses."""

    @abstractmethod
    def setup_challenge(
        self, handle: InstanceHandle, *, challenge: "Challenge", level: Optional["Level"]
    ) -> None:
        """Jalankan penyiapan challenge di dalam instance (setup_challenge.yml)."""

    @abstractmethod
    def cleanup_challenge(self, handle: InstanceHandle, *, team: str) -> None:
        """Pembersihan di dalam instance sebelum dihapus (post_challenge.yml)."""

    @abstractmethod
    def remove_access(self, handle: InstanceHandle) -> None:
        """Cabut akses jaringan (hapus port forward / security group)."""

    @abstractmethod
    def destroy_instance(self, handle: InstanceHandle) -> None:
        """Hentikan/hapus instance dan bebaskan sumber dayanya."""
