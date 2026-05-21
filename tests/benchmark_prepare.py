"""
benchmark_prepare.py — Pengujian performa fase prepare challenge
Mengukur durasi prepare level secara otomatis, 10 iterasi sekuensial.
Satu level dibuat sekali; prepare dijalankan berulang pada level yang sama
sehingga image tag level-{id}:latest di-overwrite setiap iterasi.

Penggunaan:
    # Buat level baru + benchmark 10 iterasi:
    python tests/benchmark_prepare.py --source-url https://github.com/penicili/SSTI

    # Pakai level yang sudah ada (skip pembuatan):
    python tests/benchmark_prepare.py --level-id 3

    # Custom backend URL:
    python tests/benchmark_prepare.py --backend http://192.168.1.x:8000/api/v1 \\
        --source-url https://github.com/penicili/ssti
"""

import argparse
import json
import statistics
import time
from datetime import datetime

import requests

# Config

BACKEND_URL       = "http://localhost:8000/api/v1"
ITERATIONS        = 10
POLL_INTERVAL     = 5    # detik antar polling (prepare lebih lama dari deploy)
TIMEOUT           = 900  # detik maksimum menunggu tiap iterasi (15 menit)
PAUSE_BETWEEN     = 10   # detik jeda antar iterasi


# Helpers

def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def poll_level(level_id: int, target_status: str) -> dict:
    """Poll GET /levels/{id} sampai prepare_status target tercapai."""
    deadline = time.monotonic() + TIMEOUT
    while time.monotonic() < deadline:
        resp = requests.get(f"{BACKEND_URL}/levels/{level_id}", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        status = data.get("prepare_status", "")
        log(f"  level {level_id} → {status}")
        if status == target_status:
            return data
        if status == "error":
            raise RuntimeError(f"Prepare error: {data.get('prepare_error')}")
        time.sleep(POLL_INTERVAL)
    raise TimeoutError(f"Timeout menunggu prepare_status '{target_status}' pada level {level_id}")


def create_level(source_url: str) -> int:
    """Buat level baru untuk benchmark, return level_id."""
    name = f"BenchmarkPrepare-{int(time.time())}"
    resp = requests.post(f"{BACKEND_URL}/levels", json={
        "name":       name,
        "category":   "A03:2021-Injection",
        "difficulty": "easy",
        "source_url": source_url,
        "points":     100,
    }, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    log(f"Level dibuat: id={data['id']}, name='{data['name']}'")
    return data["id"]


# Satu Iterasi

def run_iteration(iteration: int, level_id: int) -> dict:
    log(f"\n{'═'*50}")
    log(f"ITERASI {iteration}/{ITERATIONS}")
    log(f"{'═'*50}")

    log("PREPARE — mengirim request...")
    t_start = time.monotonic()
    resp = requests.post(f"{BACKEND_URL}/levels/{level_id}/prepare", timeout=10)
    resp.raise_for_status()

    poll_level(level_id, "preparing")  # tunggu background task benar-benar mulai
    poll_level(level_id, "ready")
    elapsed = round(time.monotonic() - t_start, 2)
    log(f"PREPARE selesai: {elapsed}s")
    return {"iteration": iteration, "level_id": level_id, "prepare_time": elapsed}


# Laporan

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


def print_summary(results: list):
    valid = [r for r in results if "error" not in r]

    print(f"\n{'═'*40}")
    print("HASIL PENGUJIAN PERFORMA — PREPARE")
    print(f"{'═'*40}")
    print(f"\n{'Iter':<6} {'Prepare (s)':>12}")
    print("─" * 20)

    for r in results:
        if "error" in r:
            print(f"{r['iteration']:<6} ERROR: {r['error']}")
            continue
        print(f"{r['iteration']:<6} {r['prepare_time']:>12.2f}")

    if valid:
        vals = [r["prepare_time"] for r in valid]
        print("─" * 20)
        fns = {
            "Min":       min,
            "Maks":      max,
            "Rata-rata": statistics.mean,
            "Std. Dev.": lambda x: statistics.stdev(x) if len(x) > 1 else None,
        }
        for label, fn in fns.items():
            result = fn(vals)
            print(f"{label:<10} {f'{result:.2f}' if result is not None else '—':>10}")


def save_json(results: list, source_url: str, output_path: str):
    valid = [r for r in results if "error" not in r]
    output = {
        "timestamp":  datetime.now().isoformat(),
        "iterations": ITERATIONS,
        "source_url": source_url,
        "results":    results,
        "summary":    _stats([r["prepare_time"] for r in valid]),
    }
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    log(f"Hasil disimpan ke {output_path}")


# Main

def main():
    global BACKEND_URL, ITERATIONS

    parser = argparse.ArgumentParser(description="CTF Prepare Phase Performance Benchmark")
    parser.add_argument("--backend",     default="http://localhost:8000/api/v1",
                        help="Base URL backend API")
    parser.add_argument("--source-url",  default="https://github.com/penicili/ssti",
                        help="Git URL challenge source (default: github.com/penicili/ssti)")
    parser.add_argument("--level-id",   type=int, default=None,
                        help="ID level yang sudah ada (skip pembuatan level baru)")
    parser.add_argument("--iterations", type=int, default=ITERATIONS,
                        help=f"Jumlah iterasi (default: {ITERATIONS})")
    parser.add_argument("--output",     default="tests/benchmark_prepare_results.json",
                        help="Path file output JSON")
    args = parser.parse_args()

    BACKEND_URL = args.backend.rstrip("/")
    ITERATIONS  = args.iterations

    level_id = args.level_id
    if level_id is None:
        level_id = create_level(args.source_url)

    results = []
    for i in range(1, ITERATIONS + 1):
        try:
            results.append(run_iteration(i, level_id))
        except Exception as e:
            log(f"[ERROR] Iterasi {i} gagal: {e}")
            results.append({"iteration": i, "level_id": level_id, "error": str(e)})
        if i < ITERATIONS:
            time.sleep(PAUSE_BETWEEN)

    print_summary(results)
    save_json(results, args.source_url, args.output)


if __name__ == "__main__":
    main()
