"""
monitor_resources.py — Monitor penggunaan CPU dan RAM proses backend
selama operasi prepare, deploy, dan terminate berlangsung.

CATATAN: Script ini harus dijalankan di mesin yang sama dengan backend
karena menggunakan psutil untuk membaca resource proses secara lokal.

Penggunaan:
    # Ukur deploy + terminate (level sudah ready):
    python tests/monitor_resources.py --level-id 1 --team "MonitorTeam"

    # Termasuk ukur prepare:
    python tests/monitor_resources.py --level-id 1 --team "MonitorTeam" --measure-prepare

    # Jika proses tidak terdeteksi otomatis, tentukan PID manual:
    python tests/monitor_resources.py --level-id 1 --team "MonitorTeam" --pid 1234
"""

import argparse
import json
import statistics
import threading
import time
from datetime import datetime

import psutil
import requests

# Config

BACKEND_URL     = "http://localhost:8000/api/v1"
BACKEND_PORT    = 8000
SAMPLE_INTERVAL = 1   # detik antar sampel CPU/RAM
POLL_INTERVAL   = 3   # detik antar polling status
TIMEOUT         = 600
PAUSE_BETWEEN   = 5


# Helpers

def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def find_backend_process(port: int) -> psutil.Process | None:
    """Cari proses backend berdasarkan port yang di-listen."""
    # Coba via net_connections (butuh privilege di beberapa sistem)
    try:
        for conn in psutil.net_connections(kind="inet"):
            if conn.laddr.port == port and conn.status == "LISTEN" and conn.pid:
                try:
                    return psutil.Process(conn.pid)
                except psutil.NoSuchProcess:
                    pass
    except psutil.AccessDenied:
        pass

    # Fallback: cari proses uvicorn/python yang menjalankan app
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmdline = " ".join(proc.info["cmdline"] or [])
            if "uvicorn" in cmdline or ("python" in proc.info["name"] and "app:app" in cmdline):
                return proc
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    return None


# Resource Monitor

class ResourceMonitor:
    """Sampling CPU dan RAM proses di thread terpisah."""

    def __init__(self, process: psutil.Process):
        self.process = process
        self.samples: list[dict] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self):
        self._stop.clear()
        self.samples = []
        self.process.cpu_percent()  # warm-up: nilai pertama selalu 0
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> list[dict]:
        self._stop.set()
        if self._thread:
            self._thread.join()
        return self.samples

    def _loop(self):
        while not self._stop.is_set():
            try:
                cpu = self.process.cpu_percent(interval=None)
                ram = self.process.memory_info().rss / (1024 * 1024)  # bytes → MB
                self.samples.append({
                    "cpu_pct": round(cpu, 1),
                    "ram_mb":  round(ram, 1),
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                break
            time.sleep(SAMPLE_INTERVAL)


# Poll helpers

def poll_challenge(challenge_id: int, target_status: str) -> dict:
    deadline = time.monotonic() + TIMEOUT
    while time.monotonic() < deadline:
        resp = requests.get(f"{BACKEND_URL}/challenges/{challenge_id}", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        status = data.get("deployment_status", "")
        log(f"  challenge {challenge_id} → {status}")
        if status == target_status:
            return data
        if status == "error":
            raise RuntimeError(f"Challenge error: {data.get('error_message')}")
        time.sleep(POLL_INTERVAL)
    raise TimeoutError(f"Timeout menunggu status '{target_status}'")


def poll_level(level_id: int, target_status: str) -> dict:
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
    raise TimeoutError(f"Timeout menunggu status '{target_status}'")


# Pengukuran per fase

def measure_prepare(level_id: int, monitor: ResourceMonitor) -> list[dict]:
    log(f"\n{'─'*50}\nPHASE: PREPARE\n{'─'*50}")
    monitor.start()
    resp = requests.post(f"{BACKEND_URL}/levels/{level_id}/prepare", timeout=10)
    resp.raise_for_status()
    poll_level(level_id, "preparing")
    poll_level(level_id, "ready")
    samples = monitor.stop()
    log(f"  selesai — {len(samples)} sampel diambil")
    return samples


def measure_deploy(level_id: int, team: str, monitor: ResourceMonitor) -> tuple[int, list[dict]]:
    log(f"\n{'─'*50}\nPHASE: DEPLOY\n{'─'*50}")
    monitor.start()
    resp = requests.post(f"{BACKEND_URL}/challenges", json={
        "level_id": level_id,
        "team_name": team,
    }, timeout=10)
    resp.raise_for_status()
    challenge_id = resp.json()["challenge_id"]
    log(f"  challenge_id = {challenge_id}")
    poll_challenge(challenge_id, "running")
    samples = monitor.stop()
    log(f"  selesai — {len(samples)} sampel diambil")
    return challenge_id, samples


def measure_terminate(challenge_id: int, monitor: ResourceMonitor) -> list[dict]:
    log(f"\n{'─'*50}\nPHASE: TERMINATE\n{'─'*50}")
    monitor.start()
    resp = requests.delete(f"{BACKEND_URL}/challenges/{challenge_id}", timeout=10)
    resp.raise_for_status()
    poll_challenge(challenge_id, "terminated")
    samples = monitor.stop()
    log(f"  selesai — {len(samples)} sampel diambil")
    return samples


# Statistik & laporan

def _stats(vals: list) -> dict:
    vals = [v for v in vals if v is not None]
    if not vals:
        return {"mean": None, "stdev": None, "min": None, "max": None}
    return {
        "mean":  round(statistics.mean(vals), 2),
        "stdev": round(statistics.stdev(vals), 2) if len(vals) > 1 else None,
        "min":   round(min(vals), 2),
        "max":   round(max(vals), 2),
    }


def summarize(samples: list[dict]) -> dict:
    return {
        "n_samples": len(samples),
        "cpu_pct":   _stats([s["cpu_pct"] for s in samples]),
        "ram_mb":    _stats([s["ram_mb"]  for s in samples]),
    }


def print_summary(results: dict):
    print(f"\n{'═'*68}")
    print("HASIL MONITORING SUMBER DAYA BACKEND")
    print(f"{'═'*68}")
    print(f"\n{'Fase':<12} {'CPU min':>8} {'CPU maks':>9} {'CPU mean':>9} {'RAM min':>9} {'RAM maks':>9} {'RAM mean':>9}")
    print(f"{'':12} {'(%)':>8} {'(%)':>9} {'(%)':>9} {'(MB)':>9} {'(MB)':>9} {'(MB)':>9}")
    print("─" * 68)

    for phase, s in results.items():
        cpu = s["cpu_pct"]
        ram = s["ram_mb"]
        def f(v): return f"{v:.1f}" if v is not None else "—"
        print(f"{phase:<12} {f(cpu['min']):>8} {f(cpu['max']):>9} {f(cpu['mean']):>9} "
              f"{f(ram['min']):>9} {f(ram['max']):>9} {f(ram['mean']):>9}")


def save_json(results: dict, raw: dict, output_path: str):
    out = {
        "timestamp":         datetime.now().isoformat(),
        "sample_interval_s": SAMPLE_INTERVAL,
        "summary":           results,
        "raw_samples":       raw,
    }
    with open(output_path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    log(f"Hasil disimpan ke {output_path}")


# Main

def main():
    global BACKEND_URL, BACKEND_PORT

    parser = argparse.ArgumentParser(description="Backend Resource Monitor")
    parser.add_argument("--backend",         default="http://localhost:8000/api/v1")
    parser.add_argument("--port",            type=int, default=8000,
                        help="Port backend untuk deteksi proses (default: 8000)")
    parser.add_argument("--pid",             type=int, default=None,
                        help="PID proses backend (override deteksi otomatis)")
    parser.add_argument("--level-id",        type=int, required=True)
    parser.add_argument("--team",            required=True)
    parser.add_argument("--measure-prepare", action="store_true",
                        help="Ukur fase prepare sebelum deploy/terminate")
    parser.add_argument("--output",          default="tests/monitor_resources_results.json")
    args = parser.parse_args()

    BACKEND_URL  = args.backend.rstrip("/")
    BACKEND_PORT = args.port

    # Temukan proses backend
    proc = psutil.Process(args.pid) if args.pid else find_backend_process(BACKEND_PORT)
    if not proc:
        print(f"[ERROR] Proses backend tidak ditemukan di port {BACKEND_PORT}.")
        print("        Coba jalankan ulang dengan --pid <PID>.")
        return

    log(f"Backend ditemukan: PID={proc.pid}, name='{proc.name()}'")

    monitor = ResourceMonitor(proc)
    results: dict = {}
    raw: dict = {}

    try:
        if args.measure_prepare:
            samples = measure_prepare(args.level_id, monitor)
            results["prepare"] = summarize(samples)
            raw["prepare"]     = samples
            time.sleep(PAUSE_BETWEEN)

        challenge_id, samples = measure_deploy(args.level_id, args.team, monitor)
        results["deploy"] = summarize(samples)
        raw["deploy"]     = samples
        time.sleep(PAUSE_BETWEEN)

        samples = measure_terminate(challenge_id, monitor)
        results["terminate"] = summarize(samples)
        raw["terminate"]     = samples

    except Exception as e:
        log(f"[ERROR] {e}")
        monitor.stop()

    if results:
        print_summary(results)
        save_json(results, raw, args.output)


if __name__ == "__main__":
    main()
