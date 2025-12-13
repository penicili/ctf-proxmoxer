from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

class VMInfo(BaseModel):
    """Detail informasi konfigurasi VM dari Proxmox"""
    name: Optional[str] = None
    status: Optional[str] = None
    memory: Optional[int] = None
    cores: Optional[int] = None
    net0: Optional[str] = None
    # Field lain yang mungkin dikembalikan Proxmox bisa ditambahkan dinamis 
    # atau ditangkap via extra="allow" di Config, tapi sebaiknya didefinisikan jika sering dipakai.
    
    class Config:
        extra = "allow" # Membolehkan field tambahan dari Proxmox API

class VMResult(BaseModel):
    """Hasil operasi pembuatan/manipulasi VM"""
    status: str
    vmid: int # Wajib ada jika sukses
    info: VMInfo # Wajib ada structur infonya