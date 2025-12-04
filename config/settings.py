import os
from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import Field
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "CTF Platform"
    VERSION: str = "0.1.0"
    DEBUG: bool = False
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    API_PREFIX: str = "/api/v1"
        
    # Database
    DATABASE_URL: str = "sqlite:///./ctf.db"
    
    # Proxmox
    PROXMOX_HOST: str = Field(default="192.168.1.100")
    PROXMOX_USER: str = Field(default="root@pam")
    PROXMOX_PASSWORD: str = Field(default="")
    PROXMOX_NODE: str = "pve"
    PROXMOX_VERIFY_SSL: bool = False
    
    # SSH
    SSH_USERNAME: str = "root"
    SSH_PASSWORD: str = "ctfadmin"
    SSH_PORT: int = 22
    SSH_TIMEOUT: int = 30
    
    # Challenge defaults
    DEFAULT_VM_MEMORY: int = 512
    DEFAULT_VM_CORES: int = 1
    DEFAULT_VM_STORAGE: str = "10G"
    DEFAULT_CHALLENGE_DURATION: int = 3600
    MAX_CONCURRENT_DEPLOYMENTS: int = 10
    
    # Flag
    FLAG_PREFIX: str = "CTF"
    FLAG_LENGTH: int = 32
    FLAG_CHARSET: str = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    
    # Network
    NETWORK_BASE: str = "192.168.100"
    NETWORK_MASK: int = 24
    STARTING_VMID: int = 200
    MAX_VMID: int = 500
    
    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "ctf_platform.log"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Create global settings instance
settings = Settings()