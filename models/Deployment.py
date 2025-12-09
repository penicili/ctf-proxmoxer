from typing import Optional, Dict, Any, TYPE_CHECKING
from enum import Enum
from datetime import datetime
from sqlalchemy import String, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from core.database import Base

if TYPE_CHECKING:
    from models.Challenge import Challenge


class DeploymentStatus(str, Enum):
    """Enum untuk status deployment"""
    PENDING = "pending"  # Menunggu provisioning
    CREATING = "creating"  # Sedang membuat VM
    RUNNING = "running"  # VM aktif dan berjalan
    STOPPED = "stopped"  # VM di-stop
    ERROR = "error"  # Error saat deploy/run
    TERMINATING = "terminating"  # Sedang dihapus
    TERMINATED = "terminated"  # Sudah dihapus


class Deployment(Base):
    """
    Model untuk Deployment VM
    Menyimpan info VM dan lifecycle
    """
    __tablename__ = "deployments"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    
    # Foreign Key to Challenge (One-to-One)
    challenge_id: Mapped[int] = mapped_column(ForeignKey("challenges.id", ondelete="CASCADE"), unique=True, index=True)
    
    # VM Details
    vm_id: Mapped[Optional[int]] = mapped_column(unique=True, index=True)  # Proxmox VMID
    vm_name: Mapped[Optional[str]] = mapped_column(String(100), unique=True, nullable=True)  # Unique VM name
    vm_ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)  # IPv4 atau IPv6
        
    # Status & Lifecycle
    status: Mapped[DeploymentStatus] = mapped_column(default=DeploymentStatus.PENDING, index=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Error details jika status=ERROR
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    started_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)  # Kapan VM mulai running
    stopped_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)  # Kapan VM di-stop
    terminated_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)  # Kapan VM dihapus
    
    # Relationship: One-to-One dengan Challenge
    challenge: Mapped["Challenge"] = relationship(back_populates="deployment")
    
    
    def __repr__(self):
        return f"<Deployment(id={self.id}, challenge_id={self.challenge_id}, status={self.status}, vm_id={self.vm_id})>"
    
    def is_active(self):
        """Check if deployment is currently active"""
        return self.status in [DeploymentStatus.RUNNING, DeploymentStatus.CREATING, DeploymentStatus.PENDING]
    
    def to_dict(self):
        """Convert to dictionary"""
        data = {
            "id": self.id,
            "challenge_id": self.challenge_id,
            "vm_id": self.vm_id,
            "vm_name": self.vm_name,
            "vm_ip": self.vm_ip,
            "status": self.status.value,
            "error_message": self.error_message,
            "is_active": self.is_active(),
        }        
        return data
