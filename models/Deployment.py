from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, Enum as SQLEnum
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
    Model untuk Deployment Instance
    Setiap deployment = 1 Team + 1 Challenge = 1 VM Instance
    Semua informasi team dan challenge disimpan langsung sebagai attribut
    """
    __tablename__ = "deployments"

    id = Column(Integer, primary_key=True, index=True)
    
    # Team Information
    team_name = Column(String(100), nullable=False, index=True)
    team_email = Column(String(255), nullable=True)
    team_institution = Column(String(255), nullable=True)
    
    # Challenge Information
    challenge_name = Column(String(200), nullable=False, index=True)
    challenge_category = Column(String(100), nullable=True)  # injection, xss, sqli, etc
    challenge_difficulty = Column(String(50), nullable=True)  # easy, medium, hard
    
    # VM Details
    vm_id = Column(Integer, nullable=True, unique=True, index=True)  # Proxmox VMID
    vm_name = Column(String(100), nullable=True, unique=True)  # Unique VM name
    vm_ip = Column(String(45), nullable=True)  # IPv4 atau IPv6
    vm_port = Column(Integer, nullable=True)  # Main exposed port
    vm_memory = Column(Integer, default=512, nullable=True)  # MB
    vm_cores = Column(Integer, default=1, nullable=True)
    
    # Connection Details
    ssh_port = Column(Integer, nullable=True)  # SSH port untuk access
    web_url = Column(String(255), nullable=True)  # URL untuk akses web challenge
    ssh_username = Column(String(100), nullable=True)  # Username untuk SSH
    ssh_password = Column(String(255), nullable=True)  # Password untuk SSH
    
    # Flag Management
    flag = Column(String(255), nullable=True, unique=True, index=True)  # Generated flag untuk deployment ini
    flag_submitted = Column(Boolean, default=False, nullable=False)
    flag_submitted_at = Column(DateTime, nullable=True)
    
    # Status & Lifecycle
    status = Column(SQLEnum(DeploymentStatus), default=DeploymentStatus.PENDING, nullable=False, index=True)
    error_message = Column(Text, nullable=True)  # Error details jika status=ERROR
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    started_at = Column(DateTime, nullable=True)  # Kapan VM mulai running
    stopped_at = Column(DateTime, nullable=True)  # Kapan VM di-stop
    terminated_at = Column(DateTime, nullable=True)  # Kapan VM dihapus
    
    # Metadata
    notes = Column(Text, nullable=True)  # Additional notes
    
    def __repr__(self):
        return f"<Deployment(id={self.id}, team='{self.team_name}', challenge='{self.challenge_name}', status={self.status}, vm_id={self.vm_id})>"
    
    def is_active(self):
        """Check if deployment is currently active"""
        return self.status in [DeploymentStatus.RUNNING, DeploymentStatus.CREATING, DeploymentStatus.PENDING]
    
    def to_dict(self, include_flag=False):
        """Convert to dictionary"""
        data = {
            "id": self.id,
            "team_name": self.team_name,
            "team_email": self.team_email,
            "team_institution": self.team_institution,
            "challenge_name": self.challenge_name,
            "challenge_category": self.challenge_category,
            "challenge_difficulty": self.challenge_difficulty,
            "vm_id": self.vm_id,
            "vm_name": self.vm_name,
            "vm_ip": self.vm_ip,
            "vm_port": self.vm_port,
            "vm_memory": self.vm_memory,
            "vm_cores": self.vm_cores,
            "ssh_port": self.ssh_port,
            "web_url": self.web_url,
            "ssh_username": self.ssh_username,
            "flag_submitted": self.flag_submitted,
            "flag_submitted_at": self.flag_submitted_at.isoformat() if self.flag_submitted_at else None,
            "status": self.status.value,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "stopped_at": self.stopped_at.isoformat() if self.stopped_at else None,
            "terminated_at": self.terminated_at.isoformat() if self.terminated_at else None,
            "notes": self.notes,
            "is_active": self.is_active(),
        }
        
        # Include sensitive data only when explicitly requested
        if include_flag:
            data["flag"] = self.flag
            data["ssh_password"] = self.ssh_password
        
        return data
