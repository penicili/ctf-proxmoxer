from pathlib import Path
import ansible_runner
from schemas.types.ansible_types import AnsiblePlaybookParams, AnsiblePlaybookReturn
from config.settings import Settings
from core.logging import logger


class AnsibleService:
    """
    Service yang berinteraksi dengan ansible, mulai dari setup variables sampai menjalankan berbagai playbooks
    """

    # NOTE: host proxmoxer = localhost, untuk setup baru pakai ip dari vm
    def __init__(self, settings: Settings):
        self.settings = settings
        self.project_dir = Path.cwd()
        self.ansible_dir = self.project_dir / "ansible"
        self.playbook_dir = self.ansible_dir / "playbooks"
        self.inventory_dir = self.ansible_dir / "inventory"
        self.vars_file = self.ansible_dir / "vars.yml"

        self.setup_vars()

    def setup_vars(self):
        """Setup Ansible variables file"""
        # TODO: tentuin variabel2 yang dibutuhin sama ansible, dari db/env di masukin ke file
        logger.info(f"Setting up Ansible variables...")
        vars_content = f"""proxmox_host: {self.settings.PROXMOX_HOST}
proxmox_user: {self.settings.PROXMOX_USER}
proxmox_password: {self.settings.PROXMOX_PASSWORD}
proxmox_node: {self.settings.PROXMOX_NODE}
proxmox_verify_ssl: {self.settings.PROXMOX_VERIFY_SSL}
        """
        self.vars_file.write_text(vars_content)

    def run_playbook(self, playbook, hosts, extra_vars=None):
        # TODO: Rewrite this function
        """Run ansible playbook
        :param str playbook: nama playbook yang dijalankan
        :param str hosts: nama host/group yang dituju di inventory
        :param dict extra_vars: variabel tambahan yang ingin dikirim ke playbook"""
        # Siapkan extravars
        extravars = extra_vars or {}

        # Jika ada file vars, bisa di-load juga
        if self.vars_file:
            import yaml
            with open(self.vars_file, 'r') as f:
                file_vars = yaml.safe_load(f)
                extravars.update(file_vars)

        r = ansible_runner.run(
            playbook=str(self.playbook_dir / playbook),
            extravars=extravars
        )
        return r

    def get_playbooks(self):
        """List semua playbook yang tersedia di ansible/playbooks"""
        playbooks = []
        for file in self.playbook_dir.glob("*.yml"):
            playbooks.append(file.name)
        return playbooks
