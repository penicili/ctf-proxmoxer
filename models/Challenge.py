"""
Challenge yang telah dibuat serta relasi dengan level dan deployment
"""
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime

from core.database import Base

class Challenge(Base):
    """
    Model untuk Challenge Instance
    Instance dari Level yang di-assign ke team tertentu
    Menyimpan info team, flag, dan status submission
    """
    __tablename__ = "challenges"

    id = Column(Integer, primary_key=True, index=True)
    
    # Foreign Key to Level (Many-to-One)
    level_id = Column(Integer, ForeignKey("levels.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Team Info
    team = Column(String(100), nullable=False, index=True)
    
    # Flag Management
    flag = Column(String(255), nullable=True, unique=True, index=True) 
    flag_submitted = Column(Boolean, default=False, nullable=False)
    flag_submitted_at = Column(DateTime, nullable=True)
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    level = relationship("Level", back_populates="challenges")  # Many-to-One
    deployment = relationship("Deployment", back_populates="challenge", uselist=False, cascade="all, delete-orphan")  # One-to-One
    
    def __repr__(self):
        return f"<Challenge(id={self.id}, level_id={self.level_id}, team='{self.team}', flag_submitted={self.flag_submitted})>"