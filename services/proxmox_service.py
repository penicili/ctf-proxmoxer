"""
Proxmox Service
Mengelola koneksi dan operasi dengan Proxmox VE
"""
from proxmoxer import ProxmoxAPI
from typing import Optional, List, Dict, Any
from config.settings import settings
from core.logging import logger


class ProxmoxService:
    """Service untuk mengelola koneksi dan operasi Proxmox"""
    
    def __init__(self):
        self.proxmox: Optional[ProxmoxAPI] = None
        self.node = settings.PROXMOX_NODE
        
    def connect(self) -> bool:
        """
        Membuat koneksi ke Proxmox server
        
        Returns:
            bool: True jika koneksi berhasil, False jika gagal
        """
        try:
            logger.info(f"Connecting to Proxmox at {settings.PROXMOX_HOST}...")
            
            self.proxmox = ProxmoxAPI(
                settings.PROXMOX_HOST,
                user=settings.PROXMOX_USER,
                password=settings.PROXMOX_PASSWORD,
                verify_ssl=settings.PROXMOX_VERIFY_SSL
            )
            
            # Test connection dengan get version
            version = self.proxmox.version.get()
            logger.success(f"✅ Connected to Proxmox VE {version['version']}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to Proxmox: {str(e)}")
            self.proxmox = None
            return False
    
    def is_connected(self) -> bool:
        """Check apakah sudah terkoneksi ke Proxmox"""
        return self.proxmox is not None
    
    def list_vms(self) -> List[Dict[str, Any]]:
        """
        List semua VM/Container di node
        
        Returns:
            List of VMs/Containers dengan info: vmid, name, status, type
        """
        try:
            if not self.is_connected():
                logger.warning("Not connected to Proxmox")
                return []
            
            all_vms = []
            
            # Get QEMU VMs
            try:
                qemu_vms = self.proxmox.nodes(self.node).qemu.get()
                for vm in qemu_vms:
                    all_vms.append({
                        "vmid": vm.get("vmid"),
                        "name": vm.get("name"),
                        "status": vm.get("status"),
                        "type": "qemu",
                    })
            except Exception as e:
                logger.warning(f"Failed to get QEMU VMs: {str(e)}")
            
            # Get LXC Containers
            try:
                lxc_containers = self.proxmox.nodes(self.node).lxc.get()
                for container in lxc_containers:
                    all_vms.append({
                        "vmid": container.get("vmid"),
                        "name": container.get("name"),
                        "status": container.get("status"),
                        "type": "lxc",
                    })
            except Exception as e:
                logger.warning(f"Failed to get LXC containers: {str(e)}")
            
            logger.info(f"Found {len(all_vms)} VMs/Containers")
            return all_vms
            
        except Exception as e:
            logger.error(f"Failed to list VMs: {str(e)}")
            return []


# Global instance
proxmox_service = ProxmoxService()
