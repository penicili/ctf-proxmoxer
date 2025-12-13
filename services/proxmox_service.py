"""
Proxmox Service
Mengelola koneksi dan operasi dengan Proxmox VE
"""

from proxmoxer import ProxmoxAPI
from typing import Optional, List, Dict, Any
from config.settings import Settings
from core.logging import logger
from schemas.types.Vm_types import VMResult, VMInfo
from core.exceptions import ProxmoxConnectionError, ProxmoxNodeError, VMCreationError, ResourceNotFoundError

class ProxmoxService:
    """Service untuk mengelola koneksi dan operasi Proxmox"""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.proxmox: Optional[ProxmoxAPI] = None
        self.node = settings.PROXMOX_NODE
    
    def _ensure_connected(self) -> ProxmoxAPI:
        """
        Ensure Proxmox connection is active
        
        Returns:
            ProxmoxAPI: Active Proxmox API instance
            
        Raises:
            ProxmoxConnectionError: If connection fails
        """
        if self.proxmox is not None:
            return self.proxmox

        try:
            logger.debug(f"Connecting to Proxmox at {self.settings.PROXMOX_HOST}...")
            self.proxmox = ProxmoxAPI(
                self.settings.PROXMOX_HOST,
                user=self.settings.PROXMOX_USER,
                password=self.settings.PROXMOX_PASSWORD,
                verify_ssl=self.settings.PROXMOX_VERIFY_SSL
            )
            # Verify connection
            self.proxmox.version.get()
            return self.proxmox
        except Exception as e:
            self.proxmox = None
            logger.error(f"Failed to connect to Proxmox: {str(e)}")
            raise ProxmoxConnectionError(f"Could not connect to Proxmox: {str(e)}")

    def list_vms(self) -> List[Dict[str, Any]]:
        """
        List semua VM/Container di node
        """
        try:
            proxmox = self._ensure_connected()
            all_vms = []
            
            # Get QEMU VMs
            try:
                qemu_vms = proxmox.nodes(self.node).qemu.get()
                if qemu_vms:
                    for vm in qemu_vms:
                        vm['type'] = 'qemu'
                        all_vms.append(vm)
            except Exception as e:
                logger.warning(f"Failed to fetch QEMU VMs: {e}")

            # Get LXC Containers
            try:
                lxc_containers = proxmox.nodes(self.node).lxc.get()
                if lxc_containers:
                    for container in lxc_containers:
                        container['type'] = 'lxc'
                        all_vms.append(container)
            except Exception as e:
                logger.warning(f"Failed to fetch LXC containers: {e}")

            return all_vms
            
        except ProxmoxConnectionError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error listing VMs: {e}")
            raise ProxmoxNodeError(f"Failed to list VMs: {e}")

    def create_vm(
        self, 
        level_id: int, 
        team: str, 
        time_limit: int, 
        config: Dict[str, Any]
    ) -> VMResult:
        """
        Membuat VM baru
        """
        
        team = team.strip()
        time_limit = max(1, time_limit)
        
        logger.info(f"Creating VM for team '{team}', level '{level_id}'...")
        
        try:
            proxmox = self._ensure_connected()
            vmid = self._get_next_vmid()
            vm_name = f"{team}-{level_id}-{vmid}"
            
            # Default config from settings if not provided
            memory = config.get('memory', self.settings.DEFAULT_VM_MEMORY)
            cores = config.get('cores', self.settings.DEFAULT_VM_CORES)
            
            vm_config = {
                'vmid': vmid,
                'name': vm_name,
                'memory': memory,
                'cores': cores,
                'net0': 'virtio,bridge=vmbr0',
                # TODO: Refine ISO/Template logic. Currently hardcoded fallback.
                'ide2': f"{config.get('iso', 'local:iso/ubuntu-24.04.3-live-server-amd64.iso')},media=cdrom",
                'scsi0': f"local-lvm:{config.get('disk_size', 10)}",
                'scsihw': 'virtio-scsi-pci',
                'boot': 'cdn'
            }
            
            proxmox.nodes(self.node).qemu.post(**vm_config)
            
            # Start VM
            try:
                proxmox.nodes(self.node).qemu(vmid).status.start.post()
            except Exception as e:
                # Cleanup if start fails
                logger.error(f"Failed to start VM {vmid}, rolling back...")
                proxmox.nodes(self.node).qemu(vmid).delete()
                raise VMCreationError(f"Created VM but failed to start: {e}")

            # Get Info and Return Pydantic Model
            raw_info = self.get_vm_info(vmid)
            vm_info = VMInfo(**raw_info) # Validate & Parse info

            return VMResult(
                status="success",
                vmid=vmid,
                info=vm_info
            )
            
        except Exception as e:
            logger.exception("Failed to create VM")
            raise VMCreationError(str(e))

    def _get_next_vmid(self) -> int:
        """Calculate next available VMID"""
        all_vms = self.list_vms()
        # Safe casting: filter first, then cast. 
        # Using 'or 0' is a fallback for type checker, though logic prevents it.
        existing_ids = {int(vm.get('vmid', 0)) for vm in all_vms if vm.get('vmid')}
        
        start_id = self.settings.STARTING_VMID
        max_id = self.settings.MAX_VMID
        
        for i in range(start_id, max_id):
            if i not in existing_ids:
                return i
        
        raise ProxmoxNodeError("No available VMIDs in the configured range")

    def stop_vm(self, vmid: int) -> Dict[str, Any]:
        """
        Stop a VM/Container by VMID
        
        Raises:
            ProxmoxNodeError: If stopping fails
        """
        try:
            proxmox = self._ensure_connected()
            # Check if VM exists first to provide better error message
            # This implicitly raises ResourceNotFoundError if not found
            self.get_vm_info(vmid)
            
            proxmox.nodes(self.node).qemu(vmid).status.stop.post()
            logger.info(f"VM {vmid} stopped successfully")
            return {"success": True, "vmid": vmid}
        except ResourceNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Failed to stop VM {vmid}: {e}")
            raise ProxmoxNodeError(f"Failed to stop VM {vmid}: {e}")

    def get_vm_info(self, vmid: int) -> Dict[str, Any]:
        """
        Get detailed info of a VM/Container by VMID
        
        Args:
            vmid: VMID of the VM/Container
            
        Returns:
            Dict[str, Any]: VM info dictionary
            
        Raises:
            ResourceNotFoundError: If VM is not found
            ProxmoxConnectionError: If connection fails
        """
        try:
            proxmox = self._ensure_connected()
            # 'config.get()' usually raises if VM doesn't exist on the node
            # Cast result to dict to satisfy type checker
            result = proxmox.nodes(self.node).qemu(vmid).config.get()
            if result is None:
                 raise ResourceNotFoundError(f"VM {vmid} returned empty config")
            return dict(result)
        except Exception as e:
            # Proxmoxer usually raises generic Exception or HTTPError on 404
            logger.warning(f"Failed to get info for VM {vmid}: {e}")
            raise ResourceNotFoundError(f"VM {vmid} not found or inaccessible")