from pathlib import Path
import ansible_runner
from schemas.types.ansible_types import AnsiblePlaybookParams, AnsiblePlaybookReturn
from config.settings import Settings
from core.logging import logger


class AnsibleService:
    """
    Service yang berinteraksi dengan ansible, mulai dari setup variables sampai menjalankan berbagai playbooks
    """
    def __init__(self, settings: Settings):
        self.settings = settings
        self.project_dir = Path.cwd()
        self.ansible_dir = self.project_dir / "ansible"
        self.playbook_dir = self.ansible_dir / "playbooks"
        self.inventory_dir = self.ansible_dir / "inventory"
        self.vars_file = self.ansible_dir / "vars.yml"

    def setup_vars(self):
        """Setup Ansible variables file"""
        # TODO: tentuin variabel2 yang dibutuhin sama ansible, dari db/env di masukin ke file
        vars_content = f"""
        """
        self.vars_file.write_text(vars_content)

    def run_playbook(self, playbook, hosts):
        # TODO: Rewrite this function
        """Run ansible playbook
        :param str playbook: nama playbook yang dijalankan
        :param str hosts: nama host/group yang dituju di inventory"""
        r = ansible_runner.run(
            playbook= playbook,
            vars= self.vars_file,
            hosts= hosts,
        )

    def get_playbooks(self):
        """List semua playbook yang tersedia di ansible/playbooks"""
        playbooks = []
        for file in self.playbook_dir.glob("*.yml"):
            playbooks.append(file.name)
        return playbooks