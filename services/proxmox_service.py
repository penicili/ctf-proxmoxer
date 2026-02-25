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
        Membuat VM baru dengan cara clone dari template yang sudah ada
        """
        
        team = team.strip()
        time_limit = max(1, time_limit)
        
        logger.info(f"Cloning VM for team '{team}', level '{level_id}'...")
        
        try:
            proxmox = self._ensure_connected()
            vmid = self._get_next_vmid()
            vm_name = f"{team}-{level_id}-{vmid}"

            # Template dan storage default dari settings (bisa di override via config)
            # TODO: set vmid template
            template_vmid = int(config.get('template_vmid', getattr(self.settings, 'TEMPLATE_VMID', 0)))
            if not template_vmid:
                raise VMCreationError("Template VMID tidak ditemukan. Set TEMPLATE_VMID di Settings atau kirim via config.")

            storage = config.get('storage', getattr(self.settings, 'DEFAULT_STORAGE', 'local-lvm'))
            target_node = config.get('target_node', self.node)

            # Opsi clone
            clone_opts = {
                'newid': vmid,
                'name': vm_name,
                'target': target_node,
                'storage': storage,
                # full=1 untuk full clone (copy disk), 0 untuk linked clone (butuh template template di storage yang sama)
                'full': int(config.get('full', 1)),
            }

            # Lakukan clone dari template
            logger.debug(f"Cloning template VMID {template_vmid} to VMID {vmid} on node {target_node} storage {storage}...")
            proxmox.nodes(self.node).qemu(template_vmid).clone.post(**clone_opts)

            # Optional: apply overrides setelah clone (memory, cores, net)
            memory = config.get('memory', self.settings.DEFAULT_VM_MEMORY)
            cores = config.get('cores', self.settings.DEFAULT_VM_CORES)
            net0 = config.get('net0', 'virtio,bridge=vmbr0')

            try:
                proxmox.nodes(target_node).qemu(vmid).config.post(
                    memory=memory,
                    cores=cores,
                    net0=net0
                )
            except Exception as e:
                logger.warning(f"Gagal apply config ke VM {vmid}: {e}")

            # Start VM
            try:
                proxmox.nodes(target_node).qemu(vmid).status.start.post()
            except Exception as e:
                logger.error(f"Failed to start VM {vmid}, rolling back...")
                proxmox.nodes(target_node).qemu(vmid).delete()
                raise VMCreationError(f"Cloned VM but failed to start: {e}")

            # Get Info and Return Pydantic Model
            raw_info = self.get_vm_info(vmid)
            vm_info = VMInfo(**raw_info)

            return VMResult(
                status="success",
                vmid=vmid,
                info=vm_info
            )
            
        except Exception as e:
            logger.exception("Failed to clone VM")
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