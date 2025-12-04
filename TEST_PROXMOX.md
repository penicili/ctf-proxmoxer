# Test Koneksi Proxmox

Script ini untuk menguji koneksi ke Proxmox VE server.

## Setup

1. **Copy file .env.example ke .env**
   ```bash
   Copy-Item .env.example .env
   ```

2. **Edit file .env dan isi dengan kredensial Proxmox Anda**
   ```env
   PROXMOX_HOST=192.168.1.100    # IP/hostname Proxmox server
   PROXMOX_USER=root@pam          # Username Proxmox
   PROXMOX_PASSWORD=your_password # Password Proxmox
   PROXMOX_NODE=pve               # Nama node Proxmox
   ```

3. **Jalankan test script**
   ```bash
   .\.venv\Scripts\activate
   python test_proxmox.py
   ```

## Apa yang Ditest?

✅ Koneksi ke Proxmox API  
✅ Get Proxmox version  
✅ Get node status (CPU, Memory, Uptime)  
✅ List semua VM/Container  
✅ Get next available VMID  

## Output yang Diharapkan

```
2025-12-04 10:00:00.000 | INFO     | __main__:test_proxmox_connection:15 - ============================================================
2025-12-04 10:00:00.000 | INFO     | __main__:test_proxmox_connection:16 - Testing Proxmox Connection
2025-12-04 10:00:00.000 | INFO     | __main__:test_proxmox_connection:17 - ============================================================
2025-12-04 10:00:00.000 | INFO     | __main__:test_proxmox_connection:20 - 
📋 Configuration:
2025-12-04 10:00:00.000 | INFO     | __main__:test_proxmox_connection:21 -   Host: 192.168.1.100
2025-12-04 10:00:00.000 | INFO     | __main__:test_proxmox_connection:22 -   User: root@pam
2025-12-04 10:00:00.000 | INFO     | __main__:test_proxmox_connection:23 -   Node: pve
2025-12-04 10:00:00.000 | INFO     | __main__:test_proxmox_connection:24 -   Verify SSL: False
2025-12-04 10:00:00.000 | SUCCESS  | proxmox_service:connect:37 - ✅ Connected to Proxmox VE 8.2.4
...
```

## Troubleshooting

### Error: Connection refused
- Pastikan Proxmox server running
- Cek firewall apakah port 8006 terbuka
- Pastikan IP address benar

### Error: Authentication failed
- Cek username dan password di .env
- Pastikan menggunakan format user@realm (contoh: root@pam)

### Error: SSL verification failed
- Set `PROXMOX_VERIFY_SSL=False` di .env untuk development
- Untuk production, setup proper SSL certificate
