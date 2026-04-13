"""
Test ansible_runner ProxyJump — isolate rc=4 issue.

Jalankan dari WSL di root repo:
    python3 test_runner.py

Target: VM 10.10.10.201 (challenge 24, status=running).
Ganti VM_IP / PVE_HOST / KEY_PATH sesuai kebutuhan.
"""
import ansible_runner
from pathlib import Path

# ── Config (sesuaikan dengan .env) ───────────────────────────
VM_IP    = "10.10.10.200"
VM_USER  = "testinit01"
PVE_HOST = "100.104.24.85"
PVE_USER = "root"
KEY_PATH = "/home/windaydream/.ssh/ctf_backend"
PLAYBOOK = "ansible/playbooks/prepare_challenge.yml"

# ── Build inventory (sama seperti ansible_service._build_inventory) ─
inventory = (
    f"[all]\n"
    f"{VM_IP} ansible_user={VM_USER} ansible_port=22"
    f" ansible_ssh_private_key_file={KEY_PATH}\n"
)

# ── Build envvars (sama seperti ansible_service.run_playbook) ────
envvars = {
    "ANSIBLE_HOST_KEY_CHECKING": "False",
    "ANSIBLE_SSH_ARGS": (
        f"-o ProxyCommand='ssh -i {KEY_PATH} -o StrictHostKeyChecking=no -W %h:%p {PVE_USER}@{PVE_HOST}' "
        f"-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
    ),
}

extravars = {
    "source_url":   "https://github.com/penicili/SSTI",
}

print("=" * 70)
print("INVENTORY:")
print(inventory)
print("=" * 70)
print("ENVVARS:")
for k, v in envvars.items():
    print(f"  {k}={v}")
print("=" * 70)
print(f"PLAYBOOK: {Path(PLAYBOOK).resolve()}")
print("=" * 70)

r = ansible_runner.run(
    playbook=str(Path(PLAYBOOK).resolve()),
    inventory=inventory,
    extravars=extravars,
    envvars=envvars,
    quiet=False,
)

print("=" * 70)
print(f"STATUS: {r.status}")
print(f"RC:     {r.rc}")
print(f"STATS:  {r.stats}")
print("=" * 70)