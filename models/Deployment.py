from sqlalchemy import Column, Integer, String, DateTime, Text, Enum as SQLEnum, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from enum import Enum
from core.database import Base


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

    id = Column(Integer, primary_key=True, index=True)
    
    # Foreign Key to Challenge (One-to-One)
    challenge_id = Column(Integer, ForeignKey("challenges.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    
    # VM Details
    vm_id = Column(Integer, nullable=True, unique=True, index=True)  # Proxmox VMID
    vm_name = Column(String(100), nullable=True, unique=True)  # Unique VM name
    vm_ip = Column(String(45), nullable=True)  # IPv4 atau IPv6
        
    # Status & Lifecycle
    status = Column(SQLEnum(DeploymentStatus), default=DeploymentStatus.PENDING, nullable=False, index=True)
    error_message = Column(Text, nullable=True)  # Error details jika status=ERROR
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    started_at = Column(DateTime, nullable=True)  # Kapan VM mulai running
    stopped_at = Column(DateTime, nullable=True)  # Kapan VM di-stop
    terminated_at = Column(DateTime, nullable=True)  # Kapan VM dihapus
    
    # Relationship: One-to-One dengan Challenge
    challenge = relationship("Challenge", back_populates="deployment")
    
    
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
