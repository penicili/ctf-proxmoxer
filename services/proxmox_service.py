"""
Proxmox Service
Mengelola koneksi dan operasi dengan Proxmox VE
"""

import time
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
        config: Dict[str, Any],
        vmid: Optional[int] = None,
    ) -> VMResult:
        """
        Membuat VM baru dengan cara clone dari template yang sudah ada.

        vmid: kalau sudah di-reserve sebelumnya (dari deploy_challenge_bg),
              pass langsung agar tidak terjadi double allocation.
              Kalau None, akan di-generate otomatis.
        """
        team = team.strip()
        time_limit = max(1, time_limit)

        logger.info(f"Cloning VM for team '{team}', level '{level_id}'...")

        try:
            proxmox = self._ensure_connected()
            if vmid is None:
                vmid = self._get_next_vmid()
            vm_name = f"{team}-{level_id}-{vmid}"

            template_vmid = int(config.get('template_vmid', getattr(self.settings, 'TEMPLATE_VMID', 0)))
            if not template_vmid:
                raise VMCreationError("Template VMID tidak ditemukan. Set TEMPLATE_VMID di Settings atau kirim via config.")

            storage = config.get('storage', getattr(self.settings, 'DEFAULT_STORAGE', 'local-lvm'))
            target_node = config.get('target_node', self.node)

            # Opsi clone
            is_full_clone = int(config.get('full', 0))
            clone_opts = {
                'newid': vmid,
                'name': vm_name,
                'target': target_node,
                'full': is_full_clone,
            }
            # storage hanya boleh untuk full clone
            if is_full_clone:
                clone_opts['storage'] = storage

            # Lakukan clone dari template (async task di Proxmox)
            logger.debug(f"Cloning template VMID {template_vmid} to VMID {vmid} on node {target_node} storage {storage}...")
            upid = proxmox.nodes(self.node).qemu(template_vmid).clone.post(**clone_opts)

            # Tunggu clone task selesai
            self._wait_for_task(proxmox, target_node, upid)
            logger.info(f"Clone completed: VMID {vmid}")

            # Apply overrides setelah clone
            memory = config.get('memory', self.settings.DEFAULT_VM_MEMORY)
            cores = config.get('cores', self.settings.DEFAULT_VM_CORES)
            cpu_type = config.get('cpu_type')

            # Cloud-init: static IP berdasarkan VMID (e.g. VMID 201 → 10.10.10.201)
            vm_ip = f"{self.settings.VM_SUBNET}.{vmid}"
            ipconfig0 = f"ip={vm_ip}/{self.settings.VM_NETMASK},gw={self.settings.VM_GATEWAY}"

            vm_config_opts = {
                "memory": memory,
                "cores": cores,
                "ipconfig0": ipconfig0,
            }

            if cpu_type:
                vm_config_opts["cpu"] = cpu_type

            try:
                proxmox.nodes(target_node).qemu(vmid).config.post(**vm_config_opts)
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

    def _wait_for_task(self, proxmox: ProxmoxAPI, node: str, upid: str, timeout: int = 300, interval: int = 3) -> None:
        """
        Tunggu Proxmox task selesai (polling status).

        :param upid: UPID task dari Proxmox
        :param timeout: max waktu tunggu (detik)
        :param interval: interval polling (detik)
        :raises VMCreationError: jika task gagal atau timeout
        """
        elapsed = 0
        while elapsed < timeout:
            task_status = proxmox.nodes(node).tasks(upid).status.get()
            status = task_status.get("status", "")
            if status == "stopped":
                exit_status = task_status.get("exitstatus", "")
                if exit_status == "OK":
                    return
                raise VMCreationError(f"Proxmox task failed: {exit_status}")
            time.sleep(interval)
            elapsed += interval
            logger.debug(f"Waiting for task {upid}... ({elapsed}s)")
        raise VMCreationError(f"Proxmox task timeout after {timeout}s: {upid}")

    def _get_next_vmid(self) -> int:
        """
        Dapatkan VMID berikutnya yang tersedia.

        Cek dua sumber agar tidak terjadi race condition saat concurrent deploy:
        1. Proxmox API — VM yang sudah ada (clone selesai)
        2. DB deployments — VMID yang sudah di-reserve tapi clone belum selesai
           (vm_id sudah disimpan ke DB sebelum clone dimulai)
        """
        start_id = self.settings.STARTING_VMID
        max_id   = self.settings.MAX_VMID

        # VMID yang sudah ada di Proxmox
        all_vms     = self.list_vms()
        proxmox_ids = {int(vm.get('vmid', 0)) for vm in all_vms if vm.get('vmid')}

        # VMID yang sudah di-reserve di DB (deployment aktif, clone mungkin belum selesai)
        from core.database import SessionLocal
        from models.Deployment import Deployment, DeploymentStatus
        db = SessionLocal()
        try:
            reserved = db.query(Deployment.vm_id).filter(
                Deployment.vm_id.isnot(None),
                Deployment.status.notin_([
                    DeploymentStatus.TERMINATED,
                    DeploymentStatus.ERROR,
                ])
            ).all()
            db_ids = {r.vm_id for r in reserved}
        finally:
            db.close()

        occupied = proxmox_ids | db_ids
        logger.debug(f"[vmid] Proxmox: {len(proxmox_ids)}, DB reserved: {len(db_ids)}, total occupied: {len(occupied)}")

        for vmid in range(start_id, max_id):
            if vmid not in occupied:
                return vmid

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

    def shutdown_vm(self, vmid: int, timeout: int = 120) -> None:
        """
        Graceful shutdown VM lalu tunggu sampai benar-benar stopped.
        """
        try:
            proxmox = self._ensure_connected()
            proxmox.nodes(self.node).qemu(vmid).status.shutdown.post()
            logger.info(f"Shutdown signal sent to VM {vmid}, waiting...")

            elapsed = 0
            while elapsed < timeout:
                status = proxmox.nodes(self.node).qemu(vmid).status.current.get()
                if status.get("status") == "stopped":
                    logger.info(f"VM {vmid} stopped after {elapsed}s")
                    return
                time.sleep(3)
                elapsed += 3

            # Kalau belum mati juga, force stop
            logger.warning(f"VM {vmid} did not stop after {timeout}s, forcing stop")
            proxmox.nodes(self.node).qemu(vmid).status.stop.post()
            time.sleep(5)
        except Exception as e:
            logger.error(f"Failed to shutdown VM {vmid}: {e}")
            raise ProxmoxNodeError(f"Failed to shutdown VM {vmid}: {e}")

    def convert_to_template(self, vmid: int) -> None:
        """
        Convert VM ke template.
        VM harus dalam keadaan stopped.
        """
        try:
            proxmox = self._ensure_connected()
            proxmox.nodes(self.node).qemu(vmid).template.post()
            logger.info(f"VM {vmid} converted to template")
        except Exception as e:
            logger.error(f"Failed to convert VM {vmid} to template: {e}")
            raise ProxmoxNodeError(f"Failed to convert VM {vmid} to template: {e}")

    def destroy_vm(self, vmid: int) -> None:
        """
        Destroy (hapus) VM beserta disk-nya.
        """
        try:
            proxmox = self._ensure_connected()
            proxmox.nodes(self.node).qemu(vmid).delete(purge=1)
            logger.info(f"VM {vmid} destroyed")
        except Exception as e:
            logger.error(f"Failed to destroy VM {vmid}: {e}")
            raise ProxmoxNodeError(f"Failed to destroy VM {vmid}: {e}")

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