## To do list
0. Baca dokumentasi API proxmox
1. Fitur logika Bisnis dasar backend (bikin migration, buat challange, submit challenge)
    1.1. Create Challenge
    1.2. Submit Flag
    1.3. GET Status Challenge
    1.4. Scoring
    1.4. 
2. Akses Endpoint API
3. Integrasi dengan proxmox melalui proxmox service (proxmoxer library)
4. Buat Template VM + cloud-init buat deployment challenges


## Coretan

- Vm template 
- Generate flag terus simpen di service echo yang buat nyimpen falg dalem vm nya
- Ntar dia bakal nge listen tcp
- Ntr pas submit, backend kirim tcp ke vm nya
- Kalo berhasil vmnya dimatiin