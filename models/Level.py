from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, Enum as SQLEnum
from sqlalchemy.orm import relationship
from enum import Enum
from datetime import datetime
from core.database import Base

class CategoryEnum(str, Enum):
    """Enum jenis kategori level """
    AccessControl = "A01:2021-Broken Access Control"
    Cryptography = "A02:2021-Cryptographic Failures"
    Injection = "A03:2021-Injection"
    InsecureDesign = "A04:2021-Insecure Design"
    Misconfiguration = "A05:2021-Security Misconfiguration"
    OutdatedComponents = "A06:2021-Vulnerable and Outdated Components"
    AuthenticationFailures = "A07:2021-Identification and Authentication Failures"
    IntegrityFailures = "A08:2021-Software and Data Integrity Failures"
    LoggingFailures = "A09:2021-Security Logging and Monitoring Failures"
    SSRF = "A10:2021-Server-Side Request Forgery (SSRF)"


class DifficultyEnum(str, Enum):
    """Enum untuk difficulty level"""
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    
class Level(Base):
    """
    Level/Template Model
    Template dasar untuk challenge yang bisa di-deploy untuk berbagai team
    """
    __tablename__ = "levels"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Level Info
    name = Column(String(200), nullable=False, unique=True, index=True)
    category = Column(SQLEnum(CategoryEnum), nullable=False, index=True)
    difficulty = Column(SQLEnum(DifficultyEnum), nullable=False, index=True)
    description = Column(Text, nullable=True)
    points = Column(Integer, nullable=False, default=100)
    
    # Template VM/Container Config
    template_url = Column(String(255), nullable=True)  # template url (dummy)
    
        
    # Status
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationship: One-to-Many dengan Challenge
    challenges = relationship("Challenge", back_populates="level", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Level(id={self.id}, name='{self.name}', category={self.category}, difficulty={self.difficulty})>"