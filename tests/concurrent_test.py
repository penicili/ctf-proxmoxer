"""
Concurrent Testing — CTF Platform Backend
Menguji perilaku sistem saat diakses oleh banyak pengguna bersamaan.

Skenario:
  1. Concurrent Deploy: N tim di-deploy bersamaan
  2. Constraint Concurrent: 2 request ke tim yang sama bersamaan (harus 1 di-skip)
  3. Concurrent Polling: N request status polling bersamaan

Jalankan:
    python3 tests/concurrent_test.py

Prasyarat:
    - Backend running di localhost:8000
    - Level dengan id yang READY tersedia
"""

import requests
import threading
import time
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

BACKEND = "http://localhost:8000/api/v1"
DB_PATH = "./ctf_platform.db"

# ── Helpers ────────────────────────────────────────────────────────────────────

def get(path, **kwargs):
    return requests.get(f"{BACKEND}{path}", timeout=10, **kwargs)

def post(path, **kwargs):
    return requests.post(f"{BACKEND}{path}", timeout=10, **kwargs)

def delete(path, **kwargs):
    return requests.delete(f"{BACKEND}{path}", timeout=10, **kwargs)

def db_query(sql, params=()):
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()
    return rows

def separator(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

def cleanup_test_challenges(team_prefix="ConcurrentTest", poll_interval=5, max_wait=300):
    """
    Cleanup challenge test dengan aman via API:
    1. Terminate semua challenge yang masih aktif via DELETE /challenges/{id}
    2. Poll sampai semua terminal (ERROR/TERMINATED)
    3. Tidak hapus DB langsung — biarkan sistem yang handle

    max_wait: batas waktu poll sebelum berhenti (detik)
    """
    # Ambil semua challenge test via API
    try:
        resp = get("/challenges")
        all_challenges = resp.json().get("challenges", [])
    except Exception as e:
        print(f"  [Cleanup] Gagal ambil challenges: {e}")
        return 0

    test_challenges = [
        c for c in all_challenges
        if c.get("team", "").startswith(team_prefix)
    ]

    if not test_challenges:
        return 0

    # Terminate semua yang masih aktif
    active_statuses = {"pending", "creating", "running"}
    to_terminate = [
        c for c in test_challenges
        if c.get("deployment_status", "").lower() in active_statuses
    ]

    for c in to_terminate:
        try:
            delete(f"/challenges/{c['id']}")
        except Exception:
            pass  # Mungkin sudah ERROR/TERMINATED

    # Poll sampai semua terminal
    terminal = {"error", "terminated"}
    waited   = 0
    while waited < max_wait:
        resp = get("/challenges")
        current = [
            c for c in resp.json().get("challenges", [])
            if c.get("team", "").startswith(team_prefix)
        ]
        still_active = [
            c for c in current
            if c.get("deployment_status", "").lower() not in terminal
        ]
        if not still_active:
            break
        statuses = list(set(c["deployment_status"] for c in still_active))
        print(f"  [Cleanup] Menunggu {len(still_active)} selesai (status: {statuses})... {waited}s")
        time.sleep(poll_interval)
        waited += poll_interval

    return len(test_challenges)

# ── Cari level yang bisa dipakai ───────────────────────────────────────────────

def get_ready_level():
    resp = get("/levels?is_active=true")
    levels = resp.json().get("levels", [])
    ready  = [l for l in levels if l.get("prepare_status") == "ready"]
    if not ready:
        raise RuntimeError("Tidak ada level dengan status READY. Jalankan prepare dulu.")
    return ready[0]

# ══════════════════════════════════════════════════════════════════════════════
# SKENARIO 1: Concurrent Deploy
# N tim di-deploy bersamaan menggunakan thread pool
# ══════════════════════════════════════════════════════════════════════════════

def deploy_one(level_id, team_name):
    """Deploy satu tim, kembalikan (team, status_code, duration, challenge_id)."""
    start = time.time()
    try:
        resp = post("/challenges", json={
            "level_id": level_id,
            "team_names": [team_name],
        })
        duration = time.time() - start
        data     = resp.json()
        ch_id    = data.get("results", [{}])[0].get("challenge_id", 0) if resp.ok else 0
        return {
            "team":         team_name,
            "status_code":  resp.status_code,
            "duration_s":   round(duration, 3),
            "challenge_id": ch_id,
            "skipped":      data.get("results", [{}])[0].get("skipped", False) if resp.ok else False,
            "error":        None if resp.ok else data.get("detail", str(data)),
        }
    except Exception as e:
        return {
            "team": team_name, "status_code": 0,
            "duration_s": round(time.time() - start, 3),
            "challenge_id": 0, "skipped": False, "error": str(e),
        }


def test_concurrent_deploy(level_id, n_teams=5):
    separator(f"SKENARIO 1: Concurrent Deploy ({n_teams} tim bersamaan)")
    team_names = [f"ConcurrentTest-{i+1}" for i in range(n_teams)]

    print(f"Mengirim {n_teams} request deploy BERSAMAAN...")
    start_all = time.time()

    with ThreadPoolExecutor(max_workers=n_teams) as ex:
        futures  = {ex.submit(deploy_one, level_id, t): t for t in team_names}
        results  = [f.result() for f in as_completed(futures)]

    total_time = round(time.time() - start_all, 3)

    # Urutkan berdasarkan team name
    results.sort(key=lambda r: r["team"])

    print(f"\nHasil per tim:")
    print(f"  {'Tim':<25} {'Status':>7} {'Durasi(s)':>10} {'ChallengeID':>12} {'Skipped':>8}")
    print(f"  {'-'*25} {'-'*7} {'-'*10} {'-'*12} {'-'*8}")
    for r in results:
        status_str = str(r['status_code']) if not r['error'] else f"ERR({r['error'][:20]})"
        print(f"  {r['team']:<25} {status_str:>7} {r['duration_s']:>10} {r['challenge_id']:>12} {str(r['skipped']):>8}")

    total_ok      = sum(1 for r in results if r["status_code"] == 202 and not r["skipped"])
    total_skipped = sum(1 for r in results if r["skipped"])
    total_error   = sum(1 for r in results if r["error"])

    print(f"\nRingkasan:")
    print(f"  Total waktu (wall clock): {total_time}s")
    print(f"  Berhasil di-queue  : {total_ok}")
    print(f"  Di-skip            : {total_skipped}")
    print(f"  Error              : {total_error}")

    # Cek race condition: apakah ada challenge_id duplikat?
    ch_ids = [r["challenge_id"] for r in results if r["challenge_id"] > 0]
    if len(ch_ids) != len(set(ch_ids)):
        print(f"\n  ⚠️  RACE CONDITION DETECTED: challenge_id duplikat! {ch_ids}")
    else:
        print(f"\n  ✓ Tidak ada race condition (semua challenge_id unik)")

    # Cek DB: verifikasi challenge yang masuk
    rows = db_query(
        "SELECT c.id, c.team, d.status FROM challenges c "
        "JOIN deployments d ON d.challenge_id=c.id "
        "WHERE c.team LIKE 'ConcurrentTest%' ORDER BY c.id",
    )
    print(f"\n  DB State ({len(rows)} challenge tercatat):")
    for r in rows:
        print(f"    id={r[0]}, team={r[1]}, status={r[2]}")

    return results


# ══════════════════════════════════════════════════════════════════════════════
# SKENARIO 2: Concurrent Request ke Tim yang Sama
# 2 request deploy ke tim yang sama bersamaan — hanya 1 boleh sukses
# ══════════════════════════════════════════════════════════════════════════════

def test_concurrent_same_team(level_id):
    separator("SKENARIO 2: Concurrent Request ke Tim yang Sama (constraint test)")

    team = "ConcurrentTest-SameTeam"
    n    = 3
    print(f"Mengirim {n} request deploy ke tim '{team}' BERSAMAAN...")

    with ThreadPoolExecutor(max_workers=n) as ex:
        futures = [ex.submit(deploy_one, level_id, team) for _ in range(n)]
        results = [f.result() for f in as_completed(futures)]

    deployed_count = sum(1 for r in results if r["status_code"] == 202 and not r["skipped"])
    skipped_count  = sum(1 for r in results if r["skipped"])
    conflict_count = sum(1 for r in results if r["status_code"] == 409)

    print(f"\nHasil:")
    for i, r in enumerate(results, 1):
        print(f"  Request {i}: status={r['status_code']}, skipped={r['skipped']}, ch_id={r['challenge_id']}")

    print(f"\nRingkasan:")
    print(f"  Berhasil di-queue : {deployed_count}")
    print(f"  Di-skip           : {skipped_count}")
    print(f"  Conflict (409)    : {conflict_count}")

    # Cek DB: hanya boleh ada 1 challenge aktif untuk tim ini
    rows = db_query(
        "SELECT c.id, c.team, d.status FROM challenges c "
        "JOIN deployments d ON d.challenge_id=c.id "
        "WHERE c.team = ? ORDER BY c.id",
        (team,)
    )
    active = [r for r in rows if r[2] not in ("TERMINATED", "ERROR")]
    print(f"\n  DB: {len(rows)} challenge total, {len(active)} aktif (expected: max 1)")

    if len(active) <= 1:
        print(f"  ✓ Constraint terpenuhi: tidak ada double deployment aktif")
    else:
        print(f"  ⚠️  CONSTRAINT VIOLATED: {len(active)} deployment aktif untuk tim yang sama!")
        for r in active:
            print(f"    id={r[0]}, team={r[1]}, status={r[2]}")


# ══════════════════════════════════════════════════════════════════════════════
# SKENARIO 3: Concurrent Status Polling
# N request polling bersamaan — simulasi banyak peserta polling bersamaan
# ══════════════════════════════════════════════════════════════════════════════

def poll_once(challenge_id):
    start = time.time()
    try:
        resp = get(f"/challenges/{challenge_id}")
        return {"status_code": resp.status_code, "duration_s": round(time.time() - start, 3)}
    except Exception as e:
        return {"status_code": 0, "duration_s": round(time.time() - start, 3), "error": str(e)}


def test_concurrent_polling(challenge_ids, n_concurrent=10):
    separator(f"SKENARIO 3: Concurrent Status Polling ({n_concurrent} request bersamaan)")

    if not challenge_ids:
        print("  Tidak ada challenge untuk dipolling. Skip.")
        return

    # Pakai challenge_id pertama yang tersedia, poll N kali bersamaan
    target_id = challenge_ids[0]
    print(f"  Polling challenge_id={target_id} sebanyak {n_concurrent}x bersamaan...")

    start_all = time.time()
    with ThreadPoolExecutor(max_workers=n_concurrent) as ex:
        futures = [ex.submit(poll_once, target_id) for _ in range(n_concurrent)]
        results = [f.result() for f in as_completed(futures)]
    total_time = round(time.time() - start_all, 3)

    durations    = [r["duration_s"] for r in results]
    success      = sum(1 for r in results if r["status_code"] == 200)
    avg_duration = round(sum(durations) / len(durations), 3)
    min_duration = min(durations)
    max_duration = max(durations)

    print(f"\n  Hasil ({n_concurrent} request concurrent):")
    print(f"    Berhasil (200)  : {success}/{n_concurrent}")
    print(f"    Total wall clock: {total_time}s")
    print(f"    Durasi rata-rata: {avg_duration}s")
    print(f"    Durasi minimum  : {min_duration}s")
    print(f"    Durasi maksimum : {max_duration}s")

    if success == n_concurrent:
        print(f"    ✓ Semua request berhasil")
    else:
        print(f"    ⚠️  {n_concurrent - success} request gagal")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("  CONCURRENT TESTING — CTF Platform Backend")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # Cleanup dari test sebelumnya
    cleaned = cleanup_test_challenges("ConcurrentTest")
    if cleaned:
        print(f"\n[Cleanup] Dihapus {cleaned} challenge test sebelumnya")

    # Cari level yang siap
    try:
        level = get_ready_level()
        print(f"\n[Setup] Menggunakan level: id={level['id']}, name={level['name']}")
    except RuntimeError as e:
        print(f"\n[ERROR] {e}")
        exit(1)

    level_id = level["id"]

    # ── Jalankan semua skenario ──
    results_s1 = test_concurrent_deploy(level_id, n_teams=5)

    # Ambil challenge_id yang berhasil di-create untuk skenario 3
    valid_ids = [r["challenge_id"] for r in results_s1 if r["challenge_id"] > 0]

    test_concurrent_same_team(level_id)

    test_concurrent_polling(valid_ids, n_concurrent=10)

    # ── Cleanup setelah test ──
    print(f"\n{'='*60}")
    print("  CLEANUP")
    print(f"{'='*60}")
    cleaned = cleanup_test_challenges("ConcurrentTest")
    print(f"  Dihapus {cleaned} challenge test")

    print(f"\n{'='*60}")
    print("  SELESAI")
    print(f"{'='*60}\n")
