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

    def _build_inventory(self, hosts: str, is_pve: bool = False, port_override: int = None,
                         direct: bool = False, ssh_user: str = None, ssh_key: str = None) -> str:
        """
        Build inventory string untuk ansible_runner.

        - "localhost"        → ansible_connection=local (untuk modul API)
        - direct=True        → SSH LANGSUNG ke host (public IP + key), tanpa ProxyJump.
                               Dipakai provider non-Proxmox (mis. AWS/EC2).
        - IP + is_pve=True   → SSH ke PVE host (pakai SSH key, tanpa password)
        - IP + is_pve=False  → SSH ke VM Proxmox via ProxyJump lewat PVE host
        - port_override      → override SSH port (untuk VM via port forwarding)
        - ssh_user/ssh_key   → override user/key (dipakai mode direct, mis. "ubuntu" + key pair EC2)
        """
        if hosts == "localhost":
            return "localhost ansible_connection=local,"

        # Direct SSH (mis. EC2): host terjangkau langsung tanpa bastion/ProxyJump.
        if direct:
            d_port = port_override or 22
            d_user = ssh_user or self.settings.VM_SSH_USERNAME
            d_key  = ssh_key or self.settings.SSH_KEY_PATH
            return (
                f"[all]\n"
                f"{hosts} ansible_user={d_user} ansible_port={d_port} ansible_ssh_private_key_file={d_key}\n"
            )

        port = port_override or self.settings.SSH_PORT
        key_path = self.settings.SSH_KEY_PATH

        if is_pve:
            # PVE: pakai SSH key sebagai root
            user = self.settings.SSH_USERNAME
            return (
                f"[all]\n"
                f"{hosts} ansible_user={user} ansible_port={port} ansible_ssh_private_key_file={key_path}\n"
            )
        else:
            # VM: pakai SSH key (inject via cloud-init), SSH via ProxyJump lewat PVE host
            user = self.settings.VM_SSH_USERNAME
            return (
                f"[all]\n"
                f"{hosts} ansible_user={user} ansible_port={port}"
                f" ansible_ssh_private_key_file={key_path}\n"
            )

    def run_playbook(self, playbook: str, hosts: str = "localhost", extra_vars: dict = None, is_pve: bool = False, port_override: int = None,
                     direct: bool = False, ssh_user: str = None, ssh_key: str = None):
        """
        Run ansible playbook.

        :param playbook: nama file playbook (e.g. "setup_challenge.yml")
        :param hosts: target host — "localhost" untuk API-based modules, atau IP untuk SSH
        :param extra_vars: variabel tambahan yang dikirim ke playbook
        :param is_pve: True jika target adalah PVE host (pakai PROXMOX_PASSWORD), False untuk VM (pakai SSH_PASSWORD)
        :param port_override: override SSH port (e.g. untuk VM via port forwarding)
        :param direct: True untuk SSH langsung ke host (mis. EC2 public IP), tanpa ProxyJump
        :param ssh_user: override user SSH (mode direct, mis. "ubuntu")
        :param ssh_key: override path key SSH (mode direct, mis. key pair EC2)
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

        inventory = self._build_inventory(hosts, is_pve=is_pve, port_override=port_override,
                                          direct=direct, ssh_user=ssh_user, ssh_key=ssh_key)
        playbook_path = str(self.playbook_dir / playbook)

        logger.info(f"Running playbook '{playbook}' on '{hosts}'")
        logger.info(f"Inventory: {inventory}")
        logger.info(f"Extra vars keys: {list(extravars.keys())}")

        # Build envvars — untuk VM, set ANSIBLE_SSH_ARGS agar ProxyJump jalan
        # Aktifkan callback profile_tasks supaya tiap task diukur durasinya.
        # (ANSIBLE_CALLBACKS_ENABLED untuk ansible >=2.11, CALLBACK_WHITELIST untuk versi lama)
        envvars = {
            "ANSIBLE_CALLBACKS_ENABLED": "profile_tasks",
            "ANSIBLE_CALLBACK_WHITELIST": "profile_tasks",
        }
        if direct and hosts != "localhost":
            # Direct SSH (mis. EC2): host terjangkau langsung, TANPA ProxyJump.
            # Tetap reuse koneksi (ControlPersist) + pipelining agar cepat.
            envvars["ANSIBLE_SSH_ARGS"] = (
                f"-o StrictHostKeyChecking=no "
                f"-o UserKnownHostsFile=/dev/null "
                f"-o ControlMaster=auto -o ControlPersist=120s"
            )
            envvars["ANSIBLE_PIPELINING"] = "True"
        elif hosts != "localhost" and not is_pve:
            key_path = self.settings.SSH_KEY_PATH
            pve_user = self.settings.SSH_USERNAME
            pve_host = self.settings.PROXMOX_HOST
            # ControlMaster/ControlPersist: reuse SATU koneksi SSH untuk semua task.
            # Tanpa ini tiap task membangun ulang tunnel ProxyJump (~5-24s/task overhead).
            envvars["ANSIBLE_SSH_ARGS"] = (
                f"-o ProxyCommand='ssh -i {key_path} -o StrictHostKeyChecking=no -W %h:%p {pve_user}@{pve_host}' "
                f"-o StrictHostKeyChecking=no "
                f"-o UserKnownHostsFile=/dev/null "
                f"-o ControlMaster=auto -o ControlPersist=120s"
            )
            # Pipelining: kurangi jumlah operasi SSH per task (lebih sedikit round-trip).
            envvars["ANSIBLE_PIPELINING"] = "True"

        logger.info(f"ANSIBLE_SSH_ARGS: {envvars.get('ANSIBLE_SSH_ARGS', 'not set')}")

        r = ansible_runner.run(
            playbook=playbook_path,
            inventory=inventory,
            extravars=extravars,
            envvars=envvars,
            # verbosity 1= task result, 2= input parameters, 3= SSH commands, 4= plugins and shell outputs
            verbosity=1,
        )

        # Baca stdout sekali ke list (stream hanya bisa diiterasi sekali)
        stdout_lines = list(r.stdout) if r.stdout else []

        # Log output — kalau gagal, log di INFO agar terlihat di log file
        if r.status != "successful":
            for line in stdout_lines:
                logger.info(f"[ansible] {line.rstrip()}")
            error_msg = f"Playbook '{playbook}' failed: status={r.status}, rc={r.rc}"
            if r.stats:
                error_msg += f", stats={r.stats}"
            logger.error(error_msg)
            raise AnsiblePlaybookError(error_msg)
        else:
            for line in stdout_lines:
                logger.debug(f"[ansible] {line.rstrip()}")

        # Durasi per-task diambil dari event ansible_runner (tiap event hasil
        # task punya 'duration'). Lebih andal daripada parsing stdout/profile_tasks.
        try:
            task_times: dict[str, float] = {}
            for ev in r.events:
                if ev.get("event") not in ("runner_on_ok", "runner_on_failed", "runner_on_async_ok"):
                    continue
                ed = ev.get("event_data", {}) or {}
                task = ed.get("task")
                dur  = ed.get("duration")
                if dur is None and ed.get("start") and ed.get("end"):
                    # fallback: hitung dari start/end ISO timestamp
                    from datetime import datetime as _dt
                    try:
                        dur = (_dt.fromisoformat(ed["end"]) - _dt.fromisoformat(ed["start"])).total_seconds()
                    except Exception:
                        dur = None
                if task and dur is not None:
                    task_times[task] = task_times.get(task, 0.0) + float(dur)

            if task_times:
                logger.info(f"[profile] '{playbook}' durasi per-task (urut terlama):")
                for task, secs in sorted(task_times.items(), key=lambda kv: kv[1], reverse=True):
                    logger.info(f"[profile] {secs:7.1f}s  {task}")
        except Exception as e:
            logger.warning(f"[profile] gagal menghitung durasi task: {e}")

        logger.info(f"Playbook '{playbook}' completed successfully")
        return r

    def get_playbooks(self):
        """List semua playbook yang tersedia di ansible/playbooks"""
        return [f.name for f in self.playbook_dir.glob("*.yml")]
