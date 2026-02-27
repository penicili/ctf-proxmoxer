import types

from services.ansible_service import AnsibleService
from schemas.types.ansible_types import AnsiblePlaybookParams
from config.settings import Settings


def test_run_playbook_uses_extravars_and_paths(monkeypatch, tmp_path):
    # Arrange: create service with a predictable project structure.
    service = AnsibleService(Settings())
    service.project_dir = tmp_path
    service.ansible_dir = tmp_path / "ansible"
    service.playbook_dir = service.ansible_dir / "playbooks"
    service.inventory_dir = service.ansible_dir / "inventory"
    service.playbook_dir.mkdir(parents=True)
    service.inventory_dir.mkdir(parents=True)

    playbook_name = "setup_challenge.yml"
    playbook_path = service.playbook_dir / playbook_name
    playbook_path.write_text("- hosts: all\n  tasks: []\n", encoding="utf-8")

    hosts_path = service.inventory_dir / "hosts.ini"
    hosts_path.write_text("[all]\n127.0.0.1\n", encoding="utf-8")

    request = AnsiblePlaybookParams(
        host="10.0.0.5",
        playbook_name=playbook_name,
        challenge_id=7,
        challenge_name="test-challenge",
        vulnhub_machine="lampiao",
        vm_id=101,
    )

    captured = {}

    class DummyStdout:
        def read(self):
            return "ok"

    def fake_run(**kwargs):
        captured.update(kwargs)
        return types.SimpleNamespace(
            status="successful",
            rc=0,
            stats={"ok": 1},
            stdout=DummyStdout(),
        )

    monkeypatch.setattr("ansible_runner.run", fake_run)

    # Act
    result = service.run_playbook(request)

    # Assert: ansible_runner.run called with expected params.
    assert captured["private_data_dir"] == str(service.ansible_dir)
    assert captured["playbook"] == str(playbook_path)
    assert captured["inventory"] == str(hosts_path)
    assert captured["extravars"] == {
        "target_host": "10.0.0.5",
        "challenge_id": 7,
        "challenge_name": "test-challenge",
        "vm_id": 101,
        "vulnhub_machine": "lampiao",
    }

    # Assert: return object is populated.
    assert result.success is True
    assert result.status == "successful"
    assert result.rc == 0
    assert result.stats == {"ok": 1}
    assert result.stdout == "ok"
