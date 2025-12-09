"""
Challenge yang telah dibuat serta relasi dengan level dan deployment
"""
from typing import Optional, TYPE_CHECKING
from datetime import datetime
from sqlalchemy import String, TIMESTAMP, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base

if TYPE_CHECKING:
    from models.Level import Level
    from models.Deployment import Deployment

class Challenge(Base):
    """
    Model untuk Challenge Instance
    Instance dari Level yang di-assign ke team tertentu
    Menyimpan info team, flag, dan status submission
    """
    __tablename__ = "challenges"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    
    # Foreign Key to Level (Many-to-One)
    level_id: Mapped[int] = mapped_column(ForeignKey("levels.id", ondelete="CASCADE"), index=True)
    
    # Team Info
    team: Mapped[str] = mapped_column(String(100), index=True)
    
    # Flag Management
    flag: Mapped[Optional[str]] = mapped_column(String(255), unique=True, index=True, nullable=True)
    flag_submitted: Mapped[bool] = mapped_column(default=False)
    flag_submitted_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)
    
    # Status
    is_active: Mapped[bool] = mapped_column(default=True, index=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now(), server_onupdate=func.now())
    
    # Relationships
    level_id: Mapped[int] = mapped_column(ForeignKey("levels.id", ondelete="CASCADE"), index=True)
    level: Mapped["Level"] = relationship(back_populates="challenges")  # Many-to-One
    
    deployment_id: Mapped[Optional[int]] = mapped_column(ForeignKey("deployments.id", ondelete="SET NULL"), unique=True, index=True, nullable=True)
    deployment: Mapped[Optional["Deployment"]] = relationship(back_populates="challenge", uselist=False, cascade="all, delete-orphan")  # One-to-One
    
    
    def __repr__(self) -> str:
        return f"<Challenge(id={self.id}, level_id={self.level_id}, team='{self.team}', flag_submitted={self.flag_submitted})>"