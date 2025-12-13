# CTF Proxmoxer Platform

A FastAPI-based web service for managing a Capture The Flag (CTF) platform. This system orchestrates Proxmox VE to provision and manage virtual machines (VMs) for CTF challenges, handling team assignments, flag generation, and lifecycle management.

## Project Overview

- **Backend**: Python, FastAPI
- **Database**: SQLAlchemy, Alembic, MySQL
- **Virtualization**: Proxmox VE (via `proxmoxer`)
- **Validation**: Pydantic
- **Logging**: Loguru
- **Automation**: Ansible (for Challenge Templates)

## Installation & Setup

1.  **Clone the repository**:
    ```bash
    git clone <repository-url>
    cd ctf-proxmoxer
    ```

2.  **Environment Setup**:
    ```bash
    python -m venv .venv
    # Windows
    .venv\Scripts\activate
    # Linux/Mac
    source .venv/bin/activate
    ```

3.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configuration**:
    Copy `.env.example` to `.env` and update the Proxmox and Database credentials.

5.  **Run the Application**:
    ```bash
    uvicorn app:app --host 0.0.0.0 --port 8000 --reload
    ```

---

## Tutorial: Creating Level Templates with Dynamic Flags

This guide explains how to create a VM template in Proxmox that serves as a "Level" for the CTF platform. The key requirement is that the flag must be **dynamic**—unique for each team deployed.

### Prerequisites

- Access to the Proxmox VE interface.
- Basic knowledge of Linux administration.

### Step 1: Create the Base VM

1.  In Proxmox, create a new VM.
2.  Install your desired OS (e.g., Ubuntu Server, Debian, Alpine).
3.  Configure networking so the VM has internet access during setup.

### Step 2: Install Challenge Dependencies

1.  SSH into the VM.
2.  Install necessary packages (e.g., Apache, Nginx, Docker, Python).
    ```bash
    sudo apt update && sudo apt install -y apache2 php cloud-init
    ```
3.  **Deploy your Vulnerable Application**:
    *   Place your source code in `/var/www/html` or the appropriate directory.
    *   Ensure the application is running and accessible (e.g., test `curl localhost`).

### Step 3: Configure Dynamic Flag Injection

The platform generates a unique flag for each team and injects it into the VM during deployment (via Cloud-Init User Data). You need a startup script to take this injected flag and place it where the vulnerability expects it.

1.  **Create a Flag Setup Script**:
    Create a script at `/usr/local/bin/setup-flag.sh`.

    ```bash
    #!/bin/bash
    
    # Path where Cloud-Init saves user-data
    USER_DATA_FILE="/var/lib/cloud/instance/user-data.txt"
    TARGET_FLAG_FILE="/var/www/html/flag.txt" # Change this to your challenge's flag location
    
    # Check if user-data exists
    if [ -f "$USER_DATA_FILE" ]; then
        # Read flag from user-data (assuming the whole user-data is the flag string)
        FLAG=$(cat "$USER_DATA_FILE")
        
        # Write flag to the target location
        echo "$FLAG" > "$TARGET_FLAG_FILE"
        
        # Secure the flag file (optional/context-dependent)
        chown root:root "$TARGET_FLAG_FILE"
        chmod 644 "$TARGET_FLAG_FILE"
        
        echo "Flag configured successfully."
    else
        echo "No user-data found. Using placeholder."
        echo "CTF{placeholder_flag}" > "$TARGET_FLAG_FILE"
    fi
    ```

2.  **Make it Executable**:
    ```bash
    chmod +x /usr/local/bin/setup-flag.sh
    ```

3.  **Register as a System Service** (or use `rc.local`):
    Create a systemd service to run this once on boot.
    File: `/etc/systemd/system/ctf-flag.service`

    ```ini
    [Unit]
    Description=Setup CTF Flag from Cloud-Init
    After=cloud-init.service
    
    [Service]
    Type=oneshot
    ExecStart=/usr/local/bin/setup-flag.sh
    
    [Install]
    WantedBy=multi-user.target
    ```

    Enable the service:
    ```bash
    sudo systemctl enable ctf-flag.service
    ```

### Step 4: Prepare for Templating

1.  **Clean up**:
    ```bash
    sudo apt clean
    sudo rm -rf /var/lib/apt/lists/*
    sudo truncate -s 0 /var/log/*log
    ```
2.  **Remove SSH Host Keys** (so new VMs generate their own):
    ```bash
    sudo rm /etc/ssh/ssh_host_*
    ```
3.  **Reset Machine ID**:
    ```bash
    sudo truncate -s 0 /etc/machine-id
    ```
4.  **Shutdown**:
    ```bash
    sudo poweroff
    ```

### Step 5: Convert to Template

1.  In the Proxmox GUI, right-click the VM you just shut down.
2.  Select **"Convert to Template"**.
3.  Note the **VM ID** (e.g., 9000). This ID will be used as the `template_url` or `template_id` when registering the Level in the platform database.

---

## Infrastructure as Code (Ansible)

To streamline Step 2 and Step 3, we recommend using **Ansible** to automate the creation of challenge templates.

- **Concept**: Define challenges as Ansible Playbooks (YAML).
- **Workflow**: The Python backend can trigger `ansible-runner` to spin up a temporary VM, install the challenge, and convert it to a template automatically.
- **Benefit**: Reproducible, version-controlled challenges ("Challenge-as-Code").