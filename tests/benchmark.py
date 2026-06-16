"""
benchmark.py — Pengujian performa sistem deployment CTF
Mengukur durasi prepare, deploy, dan terminate secara otomatis (sekuensial).

Hasil disimpan ke tests/results/ dengan timestamp di nama file agar mudah
dibandingkan antar-run (misal: sebelum vs sesudah fitur nginx auth).

Penggunaan:
    # Deploy + terminate 10x (level sudah ready):
    python tests/benchmark.py --level-id 1 --team "BenchmarkTeam"

    # Beri label run agar gampang dibandingkan di folder results:
    python tests/benchmark.py --level-id 1 --team "BenchmarkTeam" --label "with-auth"

    # Termasuk ukur prepare:
    python tests/benchmark.py --level-id 1 --team "BenchmarkTeam" --measure-prepare

    # Custom backend URL:
    python tests/benchmark.py --backend http://192.168.1.x:8000/api/v1 --level-id 1 --team "BenchmarkTeam"
"""

import argparse
import json
import os
import re
import statistics
import sys
import time
from datetime import datetime, timezone

import requests

# Console Windows default cp1252 tidak bisa encode karakter box-drawing (═ ─ →).
# Paksa stdout/stderr ke UTF-8 agar log tidak crash.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# Config

BACKEND_URL   = "http://localhost:8000/api/v1"
ITERATIONS    = 10
POLL_INTERVAL = 3    # detik antar polling
TIMEOUT       = 600  # detik maksimum menunggu tiap fase
PAUSE_BETWEEN = 5    # detik jeda setelah terminate sebelum iterasi berikutnya

# Saat backend sibuk menjalankan ansible_runner, latensi request bisa melonjak
# >10s. Pakai read-timeout longgar + retry agar lonjakan ini tidak menggagalkan
# iterasi (request hanya MEMBACA status, deploy sebenarnya jalan di background).
REQ_TIMEOUT   = (5, 30)  # (connect, read) detik

# Folder output (relatif terhadap lokasi file ini → tests/results)
RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")


# Helpers

def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def slugify(text: str) -> str:
    """Ubah label jadi aman untuk nama file."""
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", text).strip("-").lower()


def poll_challenge(challenge_id: int, target_status: str) -> dict:
    """Poll GET /challenges/{id} sampai status target tercapai."""
    deadline = time.monotonic() + TIMEOUT
    while time.monotonic() < deadline:
        try:
            resp = requests.get(f"{BACKEND_URL}/challenges/{challenge_id}", timeout=REQ_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            # Backend lagi sibuk (ansible_runner) — bukan kegagalan deploy. Retry.
            log(f"  challenge {challenge_id} → (backend sibuk, retry: {type(e).__name__})")
            time.sleep(POLL_INTERVAL)
            continue
        status = data.get("deployment_status", "")
        log(f"  challenge {challenge_id} → {status}")
        if status == target_status:
            return data
        if status == "error":
            raise RuntimeError(f"Challenge {challenge_id} error: {data.get('error_message')}")
        time.sleep(POLL_INTERVAL)
    raise TimeoutError(f"Timeout menunggu status '{target_status}' pada challenge {challenge_id}")


def poll_level(level_id: int, target_status: str) -> dict:
    """Poll GET /levels/{id} sampai prepare_status target tercapai."""
    deadline = time.monotonic() + TIMEOUT
    while time.monotonic() < deadline:
        resp = requests.get(f"{BACKEND_URL}/levels/{level_id}", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        status = data.get("prepare_status", "")
        log(f"  level {level_id} prepare_status → {status}")
        if status == target_status:
            return data
        if status == "error":
            raise RuntimeError(f"Level {level_id} prepare error: {data.get('prepare_error')}")
        time.sleep(POLL_INTERVAL)
    raise TimeoutError(f"Timeout menunggu prepare_status '{target_status}' pada level {level_id}")


def dt_diff(start_str: str | None, end_str: str | None) -> float | None:
    """Hitung selisih dua ISO datetime string dalam detik (server-side)."""
    if not start_str or not end_str:
        return None
    def parse(s):
        return datetime.fromisoformat(s.rstrip("Z")).replace(tzinfo=timezone.utc)
    return round((parse(end_str) - parse(start_str)).total_seconds(), 2)


def deploy_one(level_id: int, team: str) -> int:
    """
    Kirim POST /challenges dengan skema multi-tim (team_names: [..]).
    Kembalikan challenge_id tim pertama, atau raise kalau di-skip/gagal.
    """
    # Retry kalau backend lagi sibuk (timeout/connection) — POST deploy idempotent
    # secara praktis di sini karena constraint 1-aktif-per-tim mencegah duplikat.
    last_err = None
    for attempt in range(5):
        try:
            resp = requests.post(f"{BACKEND_URL}/challenges", json={
                "level_id":   level_id,
                "team_names": [team],
            }, timeout=REQ_TIMEOUT)
            resp.raise_for_status()
            break
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            last_err = e
            log(f"  POST deploy timeout (attempt {attempt+1}/5), retry...")
            time.sleep(POLL_INTERVAL)
    else:
        raise RuntimeError(f"POST /challenges gagal setelah 5x retry: {last_err}")
    body = resp.json()

    results = body.get("results", [])
    if not results:
        raise RuntimeError(f"Respons deploy tanpa results: {body}")

    first = results[0]
    if first.get("skipped"):
        raise RuntimeError(f"Deploy di-skip: {first.get('skip_reason')}")
    return first["challenge_id"]


# ── Fase Prepare ──────────────────────────────────────────────────────────────

def measure_prepare(level_id: int) -> float:
    log(f"\n{'─'*50}")
    log(f"PREPARE — level {level_id}")
    log(f"{'─'*50}")
    resp = requests.post(f"{BACKEND_URL}/levels/{level_id}/prepare", timeout=10)
    resp.raise_for_status()
    t_start = time.monotonic()
    poll_level(level_id, "ready")
    elapsed = round(time.monotonic() - t_start, 2)
    log(f"PREPARE selesai: {elapsed}s")
    return elapsed


# ── Satu Iterasi ──────────────────────────────────────────────────────────────

def run_iteration(iteration: int, level_id: int, team: str) -> dict:
    log(f"\n{'═'*50}")
    log(f"ITERASI {iteration}/{ITERATIONS}")
    log(f"{'═'*50}")

    # ── Deploy ────────────────────────────────────────────────────────────────
    log("DEPLOY — mengirim request...")
    t_deploy = time.monotonic()
    challenge_id = deploy_one(level_id, team)
    log(f"  challenge_id = {challenge_id}")

    data = poll_challenge(challenge_id, "running")
    deploy_client = round(time.monotonic() - t_deploy, 2)

    # Server-side: selisih created_at → started_at (tersimpan di DB)
    deploy_server = dt_diff(data.get("created_at"), data.get("started_at"))

    log(f"DEPLOY selesai — client: {deploy_client}s | server: {deploy_server}s")
    time.sleep(PAUSE_BETWEEN)

    # ── Terminate ─────────────────────────────────────────────────────────────
    log("TERMINATE — mengirim request...")
    t_term = time.monotonic()
    resp = requests.delete(f"{BACKEND_URL}/challenges/{challenge_id}", timeout=REQ_TIMEOUT)
    resp.raise_for_status()

    data = poll_challenge(challenge_id, "terminated")
    terminate_client = round(time.monotonic() - t_term, 2)

    # Server-side: selisih started_at → terminated_at
    terminate_server = dt_diff(data.get("started_at"), data.get("terminated_at"))

    log(f"TERMINATE selesai — client: {terminate_client}s | server: {terminate_server}s")

    return {
        "iteration":        iteration,
        "challenge_id":     challenge_id,
        "deploy_client":    deploy_client,    # waktu total deploy (sisi klien)
        "deploy_server":    deploy_server,    # waktu deploy dari DB (created_at → started_at)
        "terminate_client": terminate_client, # waktu total terminate (sisi klien)
        "terminate_server": terminate_server, # waktu terminate dari DB (started_at → terminated_at)
    }


# ── Laporan ───────────────────────────────────────────────────────────────────

def _stats(vals: list) -> dict:
    vals = [v for v in vals if v is not None]
    if not vals:
        return {"mean": None, "stdev": None, "min": None, "max": None}
    return {
        "mean":  round(statistics.mean(vals), 2),
        "stdev": round(statistics.stdev(vals), 2) if len(vals) > 1 else None,
        "min":   min(vals),
        "max":   max(vals),
    }


def print_summary(results: list, prepare_time: float | None, label: str | None):
    valid = [r for r in results if "error" not in r]

    print(f"\n{'═'*52}")
    print("HASIL PENGUJIAN PERFORMA" + (f"  [{label}]" if label else ""))
    print(f"{'═'*52}")

    if prepare_time is not None:
        print(f"\nWaktu Persiapan : {prepare_time} detik (1 pengukuran, sisi klien)")

    print(f"\n{'Iter':<6} {'Deploy (s)':>12} {'Terminate (s)':>14}")
    print("─" * 34)

    for r in results:
        if "error" in r:
            print(f"{r['iteration']:<6} ERROR: {r['error']}")
            continue
        d = f"{r['deploy_server']:.2f}"   if r.get('deploy_server')    is not None else f"{r['deploy_client']:.2f}"
        t = f"{r['terminate_server']:.2f}" if r.get('terminate_server') is not None else f"{r['terminate_client']:.2f}"
        print(f"{r['iteration']:<6} {d:>12} {t:>14}")

    if valid:
        print("─" * 34)
        fns = {
            "Rata-rata": statistics.mean,
            "Std. Dev.": lambda x: statistics.stdev(x) if len(x) > 1 else None,
            "Min":       min,
            "Max":       max,
        }
        for label_row, fn in fns.items():
            d_vals = [r["deploy_server"]    for r in valid if r.get("deploy_server")    is not None] \
                  or [r["deploy_client"]    for r in valid]
            t_vals = [r["terminate_server"] for r in valid if r.get("terminate_server") is not None] \
                  or [r["terminate_client"] for r in valid]
            def fmt(lst): return f"{fn(lst):.2f}" if lst and fn(lst) is not None else "—"
            print(f"{label_row:<10} {fmt(d_vals):>10} {fmt(t_vals):>14}")


def save_json(results: list, prepare_time: float | None, output_path: str,
              label: str | None, meta: dict):
    valid = [r for r in results if "error" not in r]
    d_vals = [r["deploy_server"]    for r in valid if r.get("deploy_server")    is not None] \
          or [r["deploy_client"]    for r in valid]
    t_vals = [r["terminate_server"] for r in valid if r.get("terminate_server") is not None] \
          or [r["terminate_client"] for r in valid]
    output = {
        "timestamp":    datetime.now().isoformat(),
        "label":        label,
        "meta":         meta,
        "iterations":   ITERATIONS,
        "prepare_time": prepare_time,
        "results":      results,
        "summary": {
            "deploy":    _stats(d_vals),
            "terminate": _stats(t_vals),
        },
    }
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, default=str)
    log(f"Hasil disimpan ke {output_path}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    global BACKEND_URL, ITERATIONS

    parser = argparse.ArgumentParser(description="CTF Deployment Performance Benchmark")
    parser.add_argument("--backend",         default="http://localhost:8000/api/v1",
                        help="Base URL backend API")
    parser.add_argument("--level-id",        type=int, required=True,
                        help="ID level yang sudah berstatus ready")
    parser.add_argument("--team",            required=True,
                        help="Nama tim yang dipakai untuk setiap iterasi deployment")
    parser.add_argument("--iterations",      type=int, default=ITERATIONS,
                        help=f"Jumlah iterasi (default: {ITERATIONS})")
    parser.add_argument("--measure-prepare", action="store_true",
                        help="Ukur waktu prepare sebelum iterasi deploy/terminate")
    parser.add_argument("--label",           default=None,
                        help="Label run (mis. 'with-auth' / 'no-auth'), masuk ke nama file & JSON")
    parser.add_argument("--output",          default=None,
                        help="Path file output JSON (default: tests/results/<timestamp>[_label].json)")
    args = parser.parse_args()

    BACKEND_URL = args.backend.rstrip("/")
    ITERATIONS  = args.iterations

    # Tentukan path output: tests/results/benchmark_<timestamp>[_label].json
    if args.output:
        output_path = args.output
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = f"_{slugify(args.label)}" if args.label else ""
        output_path = os.path.join(RESULTS_DIR, f"benchmark_{ts}{suffix}.json")

    prepare_time = None
    if args.measure_prepare:
        prepare_time = measure_prepare(args.level_id)
        time.sleep(PAUSE_BETWEEN)

    results = []
    for i in range(1, ITERATIONS + 1):
        try:
            results.append(run_iteration(i, args.level_id, args.team))
        except Exception as e:
            log(f"[ERROR] Iterasi {i} gagal: {e}")
            results.append({"iteration": i, "error": str(e)})
        time.sleep(PAUSE_BETWEEN)

    meta = {
        "backend":  BACKEND_URL,
        "level_id": args.level_id,
        "team":     args.team,
    }
    print_summary(results, prepare_time, args.label)
    save_json(results, prepare_time, output_path, args.label, meta)


if __name__ == "__main__":
    main()
