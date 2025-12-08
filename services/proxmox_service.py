"""
Proxmox Service
Mengelola koneksi dan operasi dengan Proxmox VE
"""

from proxmoxer import ProxmoxAPI
from typing import Optional, List, Dict, Any
from config.settings import settings
from core.logging import logger
from schemas.types import Vm_result


class ProxmoxService:
    """Service untuk mengelola koneksi dan operasi Proxmox"""
    
    def __init__(self):
        self.proxmox: Optional[ProxmoxAPI] = None
        self.node = settings.PROXMOX_NODE
    
    def _ensure_connected(self) -> ProxmoxAPI:
        """
        Ensure Proxmox connection is active
        
        Returns:
            ProxmoxAPI: Active Proxmox API instance
            
        Raises:
            ConnectionError: If not connected to Proxmox
        """
        if self.proxmox is None:
            raise ConnectionError("Not connected to Proxmox. Call connect() first.")
        return self.proxmox
    
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
            
            try:
                version = self.proxmox.version.get()
            except Exception as e:
                logger.exception(f"Failed to get Proxmox version")
            
            return True
            
        except Exception as e:
            logger.exception("Failed to connect to Proxmox")
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
            
            proxmox = self._ensure_connected()
            
            all_vms = []
            
            try:
                qemu_vms = proxmox.nodes(self.node).qemu.get()  
                if qemu_vms is not None:
                    for vm in qemu_vms:
                        all_vms.append({
                            "vmid": vm.get("vmid"),
                            "name": vm.get("name"),
                            "status": vm.get("status"),
                            "type": "qemu",
                        })
                else:
                    logger.warning("No QEMU VMs found")
            except Exception as e:
                logger.warning(f"Failed to get QEMU VMs: {str(e)}")
            
            try:
                lxc_containers = proxmox.nodes(self.node).lxc.get()  
                if lxc_containers is not None:
                    for container in lxc_containers:
                        all_vms.append({
                            "vmid": container.get("vmid"),
                            "name": container.get("name"),
                            "status": container.get("status"),
                            "type": "lxc",
                        })
                else:
                    logger.warning("No LXC containers found")
            except Exception as e:
                logger.warning(f"Failed to get LXC containers: {str(e)}")
            
            logger.info(f"Found {len(all_vms)} VMs/Containers")
            return all_vms
            
        except ConnectionError as e:
            logger.error(str(e))
            return []
        except Exception as e:
            logger.error(f"Failed to list VMs: {str(e)}")
            return []

    def create_vm(
        self, 
        level_id: int, 
        team: str, 
        time_limit: int, 
        config: Dict[str, Any]
    ) -> Vm_result:
        """
        Membuat VM/Container baru berdasarkan konfigurasi
        
        Args:
            level_id: ID level challenge
            team: Nama tim
            time_limit: Batas waktu dalam menit
            config: Konfigurasi VM/Container
            
        Returns:
            Vm_result: Hasil pembuatan VM/Container
            
        Raises:
            ConnectionError: If not connected to Proxmox
            ValueError: If no VMID available
        """
        # Sanitize inputs
        team = team.strip()
        time_limit = max(1, time_limit)
        
        logger.info(f"Creating VM for team '{team}', level '{level_id}' with time limit of {time_limit} minutes...")
        
        try:
            proxmox = self._ensure_connected()
            
            # Get next available VMID
            vmid = self._get_next_vmid()
            if not vmid:
                logger.error("Failed to get next available VMID")
                raise ValueError("No available VMID")
            
            vm_name = f"{team}-{level_id}-{vmid}"
            
            # Create VM configuration
            vm_config = {
                'vmid': vmid,
                'name': vm_name,
                'memory': config.get('memory', 1024),
                'cores': config.get('cores', 1),
                'net0': 'virtio,bridge=vmbr0',
                'ide2': f"{config.get('iso', 'local:iso/ubuntu-24.04.3-live-server-amd64.iso')},media=cdrom",
                'scsi0': f"local-lvm:{config.get('disk_size', 10)}",
                'scsihw': 'virtio-scsi-pci',
                'boot': 'cdn'
            }
            
            # Create the VM
            task = proxmox.nodes(self.node).qemu.post(**vm_config)  
            logger.info(f"VM creation task started: {task}")
            
            # Start the VM
            try:
                start_task = proxmox.nodes(self.node).qemu(vmid).status.start.post()  
                logger.success(f"VM {vmid} ({vm_name}) created and started successfully")
            except Exception:
                logger.exception(f"Failed to start VM {vmid} after creation, deleting VM")
                proxmox.nodes(self.node).qemu(vmid).delete() 
                raise
            
            # Get vm info
            vm_info = self._get_vm_info(vmid)
            
            return {
                "status": "success",
                "vmid": vmid,
                "info": vm_info
            }
            
        except Exception as e:
            logger.exception("Failed to create VM")
            raise

    def _get_next_vmid(self) -> int:
        """
        Get next available VMID
        
        Returns:
            int: Next available VMID, None if failed
        """
        try:
            all_vms = self.list_vms()
            
            # Extract existing VMIDs
            existing_vmids = {vm.get("vmid") for vm in all_vms if vm.get("vmid")}
            
            # Find next available VMID starting from 100
            for vmid in range(100, 10000):
                if vmid not in existing_vmids:
                    logger.debug(f"Found available VMID: {vmid}")
                    return vmid
            
            logger.error("No available VMID in range 100-9999")
            raise ValueError("No available VMID")
            
        except Exception as e:
            logger.exception(f"Failed to get next VMID")
            raise
        
    def stop_vm(self, vmid: int) -> Dict[str, Any]:
        """
        Stop a VM/Container by VMID
        
        Args:
            vmid: VMID of the VM/Container to stop
            
        Returns:
            Dict:[String, Any]: status, message and vmid
        """
        try:
            proxmox = self._ensure_connected()
            
            stop_task = proxmox.nodes(self.node).qemu(vmid).status.stop.post()  
            logger.success(f"VM {vmid} stopped successfully")
            return {
                "status": "success",
                "message": f"VM {vmid} stopped successfully",
                "vmid": vmid
            }
            
        except ConnectionError as e:
            logger.error(str(e))
            raise 
        except Exception as e:
            logger.exception(f"Failed to stop VM")
            raise


    # TODO: testing api proxmox buat bikin TypeDict data vm
    def _get_vm_info(self, vmid: int) -> Optional[Dict[str, Any]]:
        """
        Get detailed info of a VM/Container by VMID
        
        Args:
            vmid: VMID of the VM/Container
            
        Returns:
            Optional[Dict[str, Any]]: VM info dictionary, None if not found
        """
        try:
            proxmox = self._ensure_connected()
            
            vm_info = proxmox.nodes(self.node).qemu(vmid).config.get()  
            return vm_info
            
        except Exception:
            raise

# Global instance
proxmox_service = ProxmoxService()
