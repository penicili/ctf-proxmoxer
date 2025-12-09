from typing import Optional, List, TYPE_CHECKING
from enum import Enum
from datetime import datetime
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from core.database import Base

if TYPE_CHECKING:
    from models.Challenge import Challenge

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
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    
    # Level Info
    name: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    category: Mapped[CategoryEnum] = mapped_column(index=True)
    difficulty: Mapped[DifficultyEnum] = mapped_column(index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    points: Mapped[int] = mapped_column(default=100)
    
    # Template VM/Container Config
    template_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # template url (dummy)
    
    # Status
    is_active: Mapped[bool] = mapped_column(default=True, index=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship: One-to-Many dengan Challenge
    challenge: Mapped[List["Challenge"]] = relationship(back_populates="level", cascade="all, delete-orphan")
    
    def __repr__(self) -> str:
        return f"<Level(id={self.id}, name='{self.name}', category={self.category}, difficulty={self.difficulty})>"