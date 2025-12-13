## Project Overview

This project is a FastAPI-based web service that provides an API for managing a Capture The Flag (CTF) platform. It interacts with a Proxmox VE server to provision and manage virtual machines (VMs) for CTF challenges. The application uses SQLAlchemy for database interactions, Pydantic for data validation and settings management, and Loguru for logging.

### Key Technologies

*   **Backend:** Python, FastAPI
*   **Database:** SQLAlchemy, Alembic (for migrations), PyMySQL
*   **Virtualization:** Proxmox VE (via the `proxmoxer` library)
*   **Configuration:** Pydantic
*   **Other Libraries:** Paramiko (for SSH), Uvicorn (ASGI server)

### Architecture

The project follows a standard FastAPI application structure:

*   `app.py`: The main application entry point, where the FastAPI app is initialized.
*   `config/`: Contains application settings and configuration.
*   `core/`: Core components like the database engine and logging setup.
*   `models/`: SQLAlchemy database models.
*   `schemas/`: Pydantic schemas for data validation.
*   `services/`: Business logic, including the `ProxmoxService` for interacting with Proxmox.
*   `tests/`: Unit and integration tests.

## Building and Running

### Prerequisites

*   Python 3.8+
*   Proxmox VE server
*   MySQL database

### Installation

1.  Clone the repository:
    ```bash
    git clone <repository-url>
    cd ctf-proxmoxer
    ```
2.  Create and activate a virtual environment:
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows, use `.venv\Scripts\activate`
    ```
3.  Install the dependencies:
    ```bash
    pip install -r requirements.txt
    ```

### Configuration

1.  Create a `.env` file from the `.env.example`:
    ```bash
    cp .env.example .env
    ```
2.  Edit the `.env` file to match your environment, including database credentials and Proxmox connection details.

### Running the Application

To run the application, use the following command:

```bash
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

The API will be available at `http://localhost:8000`.

### Testing

The project uses `httpx` for testing. To run the tests, you can use `pytest`:

```bash
pytest
```

## Development Conventions

*   **Code Style:** The code generally follows the PEP 8 style guide.
*   **Migrations:** Database migrations are handled by Alembic. To create a new migration, use the following command:
    ```bash
    alembic revision --autogenerate -m "Your migration message"
    ```
    To apply the migrations:
    ```bash
    alembic upgrade head
    ```
*   **Logging:** The application uses the `loguru` library for logging. The log level and file can be configured in the `.env` file.
*   **Dependencies:** Project dependencies are managed in the `requirements.txt` file. After installing a new package, be sure to add it to this file:
    ```bash
    pip freeze > requirements.txt
    ```

## Roadmap & Architectural Recommendations

### 1. Critical Feature: Implement "Linked Clones"
Currently, the service creates VMs from scratch using ISOs, which is slow.
*   **Recommendation:** Change logic to **Clone** existing Templates.
*   **Implementation:** Use `proxmox.nodes(node).qemu(template_id).clone.post(full=0)` for instant provisioning.

### 2. Cloud-Init for Flag Injection
*   **Recommendation:** Pass the generated flag to the VM during provisioning.
*   **Implementation:** Inject the flag via Cloud-Init `user-data` (custom snippet) or `ipconfig` fields so the VM can configure itself on first boot.

### 3. Asynchronous Provisioning
Proxmox operations are slow and should not block the main API thread.
*   **Recommendation:** Offload VM creation to background tasks.
*   **Implementation:** Use FastAPI `BackgroundTasks`. Return a `202 Accepted` status with a `provisioning` state immediately, then update the DB when the VM is ready.

### 4. Automatic Cleanup (TTL)
*   **Recommendation:** Implement a scheduler to enforce Time-To-Live (TTL) for challenges.
*   **Implementation:** Use `APScheduler` to periodically check and stop/destroy VMs that have exceeded their `time_limit`.

### 5. Network Isolation & Access
*   **Recommendation:** secure the challenges and provide user access.
*   **Implementation:**
    *   **VLANs:** Assign unique VLANs per team to prevent cross-team attacks.
    *   **Reverse Proxy:** Use Nginx/Traefik to route domain names (e.g., `team1.ctf.local`) to the specific VM IP.

### 6. Robust Task Verification
*   **Recommendation:** Ensure Proxmox commands actually succeed.
*   **Implementation:** Capture the UPID (Task ID) from Proxmox API calls and poll the task status endpoint until completion before marking the challenge as `active`.

### 7. Ansible Challenge Pipeline
*   **Recommendation:** Use Ansible for creating the "Golden Image" templates that Linked Clones will use.
*   **Implementation:**
    *   Use `ansible-runner` to execute Playbooks programmatically from the Python backend.
    *   Create a "Template Builder" service where admins can trigger a build: `Python -> Ansible -> Proxmox VM -> Install Challenge -> Convert to Template`.
    *   This ensures "Challenge-as-Code" (Playbooks stored in Git) and consistent, reproducible challenge environments.
