## Project Overview

This project is a FastAPI-based web service that provides an API for managing a Capture The Flag (CTF) platform. It interacts with a Proxmox VE server to provision and manage virtual machines (VMs) for CTF challenges. The application uses SQLAlchemy for database interactions, Pydantic for data validation and settings management, and Loguru for logging.

### Key Technologies

*   **Backend:** Python, FastAPI
*   **Database:** SQLAlchemy, Alembic (for migrations), PyMySQL
*   **Virtualization:** Proxmox VE (via the `proxmoxer` library)
*   **Configuration:** Ansible (for VM configuration), Pydantic
*   **Other Libraries:** ansible-runner, Paramiko, Uvicorn

### Architecture

The project follows a standard FastAPI application structure:

*   `app.py`: The main application entry point.
*   `ansible/`: Ansible playbooks, inventory, and configuration (`ansible.cfg`).
*   `config/`: Application settings (`settings.py`).
*   `core/`: Core components (Database, Logging, Exceptions).
*   `models/`: SQLAlchemy database models.
*   `schemas/`: Pydantic schemas for request/response validation.
    *   `types/`: Shared Pydantic models (`Vm_types`, `Ansible_types`).
*   `services/`: Business logic.
    *   `proxmox_service.py`: Wrapper for Proxmox API.
    *   `ansible_service.py`: Wrapper for `ansible-runner`.
    *   `challange_service.py`: Orchestrator for Challenge Lifecycle.

## Building and Running

### Prerequisites

*   Python 3.10+
*   Proxmox VE server
*   MySQL database
*   **Linux Environment** (WSL2 or Docker) is required for `ansible-runner`.

### Installation

1.  Clone the repository:
    ```bash
    git clone <repository-url>
    cd ctf-proxmoxer
    ```
2.  Create and activate a virtual environment:
    ```bash
    python -m venv .venv
    source .venv/bin/activate
    ```
3.  Install the dependencies:
    ```bash
    pip install -r requirements.txt
    ```

### Configuration

1.  Create a `.env` file from `.env.example`.
2.  Ensure `ansible/ansible.cfg` has `host_key_checking = False` for development.

### Running the Application

```bash
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

## Recent Changes & Refactoring (December 2025)

### 1. Robust Service Layer
*   **No Silent Failures:** Services now raise specific exceptions (`ResourceNotFoundError`, `VMCreationError`) instead of returning `None`.
*   **Type Safety:** Migrated all `TypedDict` schemas to **Pydantic Models**.
*   **Pydantic Integration:** Services now return Pydantic objects, ensuring runtime validation and cleaner dot-notation access.

### 2. Ansible Integration
*   **Infrastructure as Code:** Added `AnsibleService` to configure VMs post-creation.
*   **Workflow:**
    1.  `ProxmoxService` creates VM.
    2.  `ChallengeService` generates a random Flag.
    3.  `AnsibleService` runs `setup_challenge.yml` playbook to inject the flag and install services (e.g., Nginx).
*   **Tech Stack:** Uses `ansible-runner` to execute playbooks programmatically from Python.

## Roadmap

### 1. Critical Feature: Implement "Linked Clones"
Currently, the service creates VMs from scratch using ISOs, which is slow.
*   **Recommendation:** Change logic to **Clone** existing Templates.
*   **Implementation:** Use `proxmox.nodes(node).qemu(template_id).clone.post(full=0)` for instant provisioning.

### 2. Dynamic IP Resolution
*   **Current State:** Ansible assumes `vm.name` is resolvable.
*   **Next Step:** Implement logic to retrieve the actual IP address of the newly created VM (via QEMU Guest Agent or polling Proxmox API) before triggering Ansible.

### 3. Asynchronous Provisioning
Proxmox and Ansible operations are slow (blocking).
*   **Recommendation:** Offload `create_challenge` to background tasks (Celery or FastAPI BackgroundTasks).
*   **Implementation:** Return `202 Accepted` immediately, process in background, and update DB status via Webhook or Polling.

### 4. Automatic Cleanup (TTL)
*   **Recommendation:** Implement a scheduler to enforce Time-To-Live (TTL) for challenges.
*   **Implementation:** Use `APScheduler` to periodically check and stop/destroy VMs that have exceeded their `time_limit`.

### 5. Network Isolation & Access
*   **Recommendation:** Secure the challenges and provide user access.
*   **Implementation:** VLANs per team and Reverse Proxy (Nginx/Traefik).