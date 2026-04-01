from pathlib import Path
import ansible_runner
from config.settings import Settings
from core.logging import logger
from core.exceptions import AnsiblePlaybookError


class AnsibleService:
    """
    Service yang berinteraksi dengan Ansible.

    Konsep inventory:
    - hosts="localhost"  → playbook jalan lokal, biasanya untuk modul yang
      berkomunikasi via API (community.proxmox). Inventory: localhost dengan
      ansible_connection=local.
    - hosts=<IP>         → playbook jalan via SSH ke target (VM atau PVE host).
      SSH credentials diambil dari Settings (SSH_USERNAME, SSH_PASSWORD, SSH_PORT).
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.project_dir = Path.cwd()
        self.ansible_dir = self.project_dir / "ansible"
        self.playbook_dir = self.ansible_dir / "playbooks"
        self.vars_file = self.ansible_dir / "vars.yml"

        self.setup_vars()

    def setup_vars(self):
        """Setup Ansible variables file (proxmox credentials dll)"""
        logger.info("Setting up Ansible variables...")
        vars_content = (
            f"proxmox_host: {self.settings.PROXMOX_HOST}\n"
            f"proxmox_user: {self.settings.PROXMOX_USER}\n"
            f"proxmox_password: {self.settings.PROXMOX_PASSWORD}\n"
            f"proxmox_node: {self.settings.PROXMOX_NODE}\n"
            f"proxmox_verify_ssl: {self.settings.PROXMOX_VERIFY_SSL}\n"
        )
        self.vars_file.write_text(vars_content)

    def _build_inventory(self, hosts: str, is_pve: bool = False, port_override: int = None) -> str:
        """
        Build inventory string untuk ansible_runner.

        - "localhost"        → ansible_connection=local (untuk modul API)
        - IP + is_pve=True   → SSH ke PVE host (pakai SSH key, tanpa password)
        - IP + is_pve=False  → SSH ke VM (pakai SSH_PASSWORD)
        - port_override      → override SSH port (untuk VM via port forwarding)
        """
        if hosts == "localhost":
            return "localhost ansible_connection=local,"

        user = self.settings.SSH_USERNAME
        port = port_override or self.settings.SSH_PORT

        if is_pve:
            # PVE: pakai SSH key (no password)
            key_path = self.settings.SSH_KEY_PATH
            return (
                f"[all]\n"
                f"{hosts} ansible_user={user} ansible_port={port} ansible_ssh_private_key_file={key_path}\n"
            )
        else:
            # VM: pakai password, via port forwarding di PVE host
            password = self.settings.SSH_PASSWORD
            return (
                f"[all]\n"
                f"{hosts} ansible_user={user} ansible_password={password} ansible_port={port}\n"
            )

    def run_playbook(self, playbook: str, hosts: str = "localhost", extra_vars: dict = None, is_pve: bool = False, port_override: int = None):
        """
        Run ansible playbook.

        :param playbook: nama file playbook (e.g. "setup_challenge.yml")
        :param hosts: target host — "localhost" untuk API-based modules, atau IP untuk SSH
        :param extra_vars: variabel tambahan yang dikirim ke playbook
        :param is_pve: True jika target adalah PVE host (pakai PROXMOX_PASSWORD), False untuk VM (pakai SSH_PASSWORD)
        :param port_override: override SSH port (e.g. untuk VM via port forwarding)
        :raises AnsiblePlaybookError: jika playbook gagal (status != "successful")
        """
        extravars = extra_vars or {}

        # Load vars file (proxmox credentials dll)
        if self.vars_file.exists():
            import yaml
            with open(self.vars_file, "r") as f:
                file_vars = yaml.safe_load(f)
                if file_vars:
                    extravars.update(file_vars)

        inventory = self._build_inventory(hosts, is_pve=is_pve, port_override=port_override)
        playbook_path = str(self.playbook_dir / playbook)

        logger.info(f"Running playbook '{playbook}' on '{hosts}'")
        logger.debug(f"Inventory: {inventory}")
        logger.debug(f"Extra vars keys: {list(extravars.keys())}")

        r = ansible_runner.run(
            playbook=playbook_path,
            inventory=inventory,
            extravars=extravars,
        )

        # Log output
        if r.stdout:
            for line in r.stdout:
                logger.debug(f"[ansible] {line}")

        # Check result
        if r.status != "successful":
            error_msg = f"Playbook '{playbook}' failed: status={r.status}, rc={r.rc}"
            # Coba ambil stderr/error events untuk detail
            if r.stats:
                error_msg += f", stats={r.stats}"
            logger.error(error_msg)
            raise AnsiblePlaybookError(error_msg)

        logger.info(f"Playbook '{playbook}' completed successfully")
        return r

    def get_playbooks(self):
        """List semua playbook yang tersedia di ansible/playbooks"""
        return [f.name for f in self.playbook_dir.glob("*.yml")]
