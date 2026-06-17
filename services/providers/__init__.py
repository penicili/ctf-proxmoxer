"""
Provider abstraction untuk penyediaan infrastruktur challenge.

Pakai `get_provider(settings)` untuk memperoleh implementasi sesuai
`settings.PROVIDER` (default: "proxmox").
"""
from config.settings import Settings
from services.providers.base import (
    InfraProvider,
    ReservedInstance,
    InstanceHandle,
    AccessInfo,
)
from services.providers.proxmox_provider import ProxmoxProvider

__all__ = [
    "InfraProvider",
    "ReservedInstance",
    "InstanceHandle",
    "AccessInfo",
    "ProxmoxProvider",
    "get_provider",
]


def get_provider(settings: Settings) -> InfraProvider:
    """Factory: kembalikan InfraProvider sesuai settings.PROVIDER."""
    name = (getattr(settings, "PROVIDER", "proxmox") or "proxmox").lower()
    if name == "proxmox":
        return ProxmoxProvider(settings)
    # Pengembangan lanjutan:
    # if name == "aws":
    #     from services.providers.aws_provider import AWSProvider
    #     return AWSProvider(settings)
    raise ValueError(f"PROVIDER tidak dikenal: '{name}' (pilihan: proxmox)")
