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
            logger.success(f"✅ Connected to Proxmox VE {version['version']} at {settings.PROXMOX_HOST}")
            
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

    def create_vm(self, config: Dict[str, Any]) -> Optional[int]:
        """
        Membuat VM/Container baru berdasarkan konfigurasi
        
        Args:
            config (Dict[str, Any]): Konfigurasi VM/Container
            
        Returns:
            Optional[int]: VMID dari VM/Container yang dibuat, None jika gagal
        """
        
        team = config.get("team", "unknown")
        challenge = config.get("challenge", "unknown")
        time_minutes = config.get("time", "120")
        
        logger.info(f"Creating VM for team '{team}', challenge '{challenge}' with time limit of {time_minutes} minutes...")
        
        try:
            if not self.is_connected():
                logger.error("Not connected to Proxmox")
                return None
            
            # Get next available VMID
            vmid = self._get_next_vmid()
            if not vmid:
                logger.error("Failed to get next available VMID")
                return None
            
            vm_name = f"{team}-{challenge}-{vmid}"
            
            # Create VM configuration
            vm_config = {
                'vmid': vmid,
                'name': vm_name,
                'memory': config.get('memory', 1024),
                'cores': config.get('cores', 1),
                'net0': 'virtio,bridge=vmbr0',
                'ide2': f"{config.get('iso', 'local:iso/ubuntu-24.04.3-live-server-amd64.iso')},media=cdrom",
                'scsi0': f"local-lvm:{config.get('disk_size', 20)}",
                'scsihw': 'virtio-scsi-pci',
                'boot': 'cdn'
            }
            
            # Create the VM
            task = self.proxmox.nodes(self.node).qemu.post(**vm_config)
            logger.info(f"VM creation task started: {task}")
            
            # Start the VM
            start_task = self.proxmox.nodes(self.node).qemu(vmid).status.start.post()
            logger.success(f"✅ VM {vmid} ({vm_name}) created and started successfully")
            
            return vmid
            
        except Exception as e:
            logger.error(f"Failed to create VM: {str(e)}")
            return None
        
        pass

    def _get_next_vmid(self) -> Optional[int]:
        """
        Get next available VMID
                
        Returns:
            Optional[int]: Next available VMID, None if failed
        """
        try:
            if not self.is_connected():
                return None
            
            # Get all existing VMIDs
            existing_vmids = set()
            
            # Get QEMU VMIDs
            try:
                qemu_vms = self.proxmox.nodes(self.node).qemu.get()
                for vm in qemu_vms:
                    existing_vmids.add(vm.get("vmid"))
            except Exception:
                pass
            
            # Get LXC VMIDs
            try:
                lxc_containers = self.proxmox.nodes(self.node).lxc.get()
                for container in lxc_containers:
                    existing_vmids.add(container.get("vmid"))
            except Exception:
                pass
            
            # Find next available VMID starting from 100
            for vmid in range(100, 10000):
                if vmid not in existing_vmids:
                    return vmid
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get next VMID: {str(e)}")
            return None

    def stop_vm(self, vmid: int) -> bool:
        """
        Stop a VM/Container by VMID
        
        Args:
            vmid (int): VMID of the VM/Container to stop
            
        Returns:
            bool: True if stopped successfully, False otherwise
        """
        try:
            if not self.is_connected():
                logger.error("Not connected to Proxmox")
                return False
            
            stop_task = self.proxmox.nodes(self.node).qemu(vmid).status.stop.post()
            logger.success(f"✅ VM {vmid} stopped successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to stop VM {vmid}: {str(e)}")
            return False

    
# Global instance
proxmox_service = ProxmoxService()
