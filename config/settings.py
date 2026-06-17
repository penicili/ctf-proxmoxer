import os
from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import Field, ConfigDict


class Settings(BaseSettings):

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )
    
    # Application
    APP_NAME: str = "CTF Platform"
    VERSION: str = "0.1.0"
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    API_PREFIX: str = "/api/v1"
        
    # Database
    DB_PLATFORM: str = "sqlite"
    DB_USER: str = "user"
    DB_PASSWORD: str = "password"
    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 3306
    DB_DATABASE: str = "ctf_db"

    DB_URL: str= "sqlite:///./ctf_platform.db"

    # Infrastructure provider: "proxmox" (default) atau "aws" (pengembangan lanjutan)
    PROVIDER: str = "proxmox"

    # Proxmox
    PROXMOX_HOST: str = "192.168.1.102"
    PROXMOX_USER: str = "root@pam"
    PROXMOX_PASSWORD: str = "Apakah@55"
    PROXMOX_NODE: str = "pve"
    PROXMOX_VERIFY_SSL: bool = False
    
    # SSH — PVE host
    SSH_USERNAME: str = "root"
    SSH_KEY_PATH: str = "~/.ssh/id_rsa"
    SSH_PORT: int = 22
    SSH_TIMEOUT: int = 30

    # SSH — VM (cloud-init user)
    VM_SSH_USERNAME: str = "user"
    
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
    
    # Proxmox VM defaults
    TEMPLATE_VMID: int = 9000
    STARTING_VMID: int = 200
    MAX_VMID: int = 500
    PUBLIC_BRIDGE: str = "vmbr0"
    MANAGEMENT_BRIDGE: str = "vmbr1"

    # Network — VM internal (cloud-init static IP)
    VM_SUBNET: str = "10.10.10"
    VM_GATEWAY: str = "10.10.10.1"
    VM_NETMASK: int = 24

    # Network — NAT port forwarding
    PVE_PUBLIC_IP: str = "192.168.1.102"
    SSH_PORT_BASE: int = 22000
    HTTP_PORT_BASE: int = 8000
    
    # Docker Registry + CI Runner
    REGISTRY_HOST: str = "10.10.10.5:5000"
    CI_RUNNER_IP: str = "10.10.10.110"

    # CTFd API
    CTFD_URL: str = "http://localhost:4000"
    CTFD_API_TOKEN: str = ""

    # AWS (dipakai saat PROVIDER="aws"). Kredensial sebaiknya diisi via .env (gitignored).
    AWS_REGION: str = "ap-southeast-1"
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_AMI_ID: str = ""               # AMI dengan docker + nginx (atau base Ubuntu + playbook install)
    AWS_INSTANCE_TYPE: str = "t3.micro"
    AWS_SUBNET_ID: str = ""            # kosong = default subnet VPC
    AWS_SECURITY_GROUP_ID: str = ""    # SG yang mengizinkan porta 80 (challenge) + 22 (Ansible)
    AWS_KEY_PAIR_NAME: str = ""        # nama EC2 key pair (untuk SSH)
    AWS_SSH_USER: str = "ubuntu"       # user SSH pada AMI (ubuntu / ec2-user)
    AWS_SSH_KEY_PATH: str = ""         # path lokal private key .pem (untuk Ansible)

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "ctf_platform.log"


# Create global settings instance
settings = Settings()