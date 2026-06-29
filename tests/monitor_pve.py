"""
monitor_pve.py — Monitor penggunaan CPU dan RAM HOST Proxmox per fase
(baseline idle → prepare → deploy → terminate).

Berbeda dari monitor_resources.py: skrip itu mengukur proses BACKEND (psutil
lokal); skrip INI mengukur resource HOST PROXMOX secara remote lewat proxmoxer
(nodes(node).status). Keduanya melengkapi NF-2 (Efisiensi Sumber Daya).

Koneksi & kredensial Proxmox di-reuse dari config.settings + ProxmoxService,
jadi tidak perlu SSH ke PVE. Pemicu prepare/deploy/terminate lewat API backend.

Penggunaan:
    # Tanpa argumen (default: --level-id 2 --team testteam-A):
    python tests/monitor_pve.py

    # Sertakan fase prepare (jika level belum ready / ingin mengukur prepare):
    python tests/monitor_pve.py --measure-prepare

    # Baseline idle 20 dtk, interval sampling 2 dtk:
    python tests/monitor_pve.py --baseline-seconds 20 --interval 2
"""

import argparse
import json
import os
import statistics
import sys
import threading
import time
from datetime import datetime

import requests

# Config

BACKEND_URL     = "http://localhost:8000/api/v1"
SAMPLE_INTERVAL = 2    # detik antar sampel CPU/RAM host
POLL_INTERVAL   = 3    # detik antar polling status deployment
TIMEOUT         = 600
PAUSE_BETWEEN   = 5

# Folder output (relatif terhadap lokasi file ini → tests/results)
RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")


# Helpers

def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def get_proxmox():
    """Reuse koneksi & node dari ProxmoxService (tanpa SSH)."""
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from config.settings import settings
    from services.proxmox_service import ProxmoxService

    svc = ProxmoxService(settings)
    proxmox = svc._ensure_connected()
    if proxmox is None:
        raise RuntimeError("Gagal konek ke Proxmox (cek PROXMOX_HOST/USER/PASSWORD di settings).")
    return proxmox, svc.node


# Host Resource Monitor

class HostMonitor:
    """Sampling CPU% dan RAM host Proxmox di thread terpisah via proxmoxer."""

    def __init__(self, proxmox, node: str):
        self.proxmox = proxmox
        self.node = node
        self.samples: list[dict] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self):
        self._stop.clear()
        self.samples = []
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
                st = self.proxmox.nodes(self.node).status.get()
                cpu = float(st.get("cpu", 0)) * 100                      # fraksi → %
                mem = st.get("memory", {}) or {}
                used_mb  = float(mem.get("used", 0))  / (1024 * 1024)    # bytes → MB
                total_mb = float(mem.get("total", 0)) / (1024 * 1024)
                self.samples.append({
                    "cpu_pct":      round(cpu, 1),
                    "ram_used_mb":  round(used_mb, 1),
                    "ram_total_mb": round(total_mb, 1),
                })
            except Exception as e:
                log(f"  [WARN] gagal baca status host: {e}")
            time.sleep(SAMPLE_INTERVAL)


# Poll helpers (status via API backend)

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

def measure_baseline(monitor: HostMonitor, seconds: int) -> list[dict]:
    log(f"\n{'─'*50}\nPHASE: BASELINE (idle {seconds}s)\n{'─'*50}")
    monitor.start()
    time.sleep(seconds)
    samples = monitor.stop()
    log(f"  selesai — {len(samples)} sampel diambil")
    return samples


def measure_prepare(level_id: int, monitor: HostMonitor) -> list[dict]:
    log(f"\n{'─'*50}\nPHASE: PREPARE\n{'─'*50}")
    monitor.start()
    resp = requests.post(f"{BACKEND_URL}/levels/{level_id}/prepare", timeout=10)
    resp.raise_for_status()
    poll_level(level_id, "preparing")
    poll_level(level_id, "ready")
    samples = monitor.stop()
    log(f"  selesai — {len(samples)} sampel diambil")
    return samples


def measure_deploy(level_id: int, team: str, monitor: HostMonitor) -> tuple[int, list[dict]]:
    log(f"\n{'─'*50}\nPHASE: DEPLOY\n{'─'*50}")
    monitor.start()
    resp = requests.post(f"{BACKEND_URL}/challenges", json={
        "level_id": level_id,
        "team_names": [team],
    }, timeout=10)
    resp.raise_for_status()
    challenge_id = resp.json()["results"][0]["challenge_id"]
    log(f"  challenge_id = {challenge_id}")
    poll_challenge(challenge_id, "running")
    samples = monitor.stop()
    log(f"  selesai — {len(samples)} sampel diambil")
    return challenge_id, samples


def measure_terminate(challenge_id: int, monitor: HostMonitor) -> list[dict]:
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
        "n_samples":   len(samples),
        "cpu_pct":     _stats([s["cpu_pct"]     for s in samples]),
        "ram_used_mb": _stats([s["ram_used_mb"] for s in samples]),
    }


def print_summary(results: dict, baseline_ram: float | None):
    print(f"\n{'═'*72}")
    print("HASIL MONITORING SUMBER DAYA HOST PROXMOX")
    print(f"{'═'*72}")
    print(f"\n{'Fase':<12} {'CPU min':>8} {'CPU maks':>9} {'CPU mean':>9} "
          f"{'RAM min':>9} {'RAM maks':>9} {'RAM mean':>9} {'ΔRAM':>9}")
    print(f"{'':12} {'(%)':>8} {'(%)':>9} {'(%)':>9} {'(MB)':>9} {'(MB)':>9} {'(MB)':>9} {'(MB)':>9}")
    print("─" * 72)

    def f(v): return f"{v:.1f}" if v is not None else "—"
    for phase, s in results.items():
        cpu = s["cpu_pct"]; ram = s["ram_used_mb"]
        dram = (ram["mean"] - baseline_ram) if (baseline_ram is not None and ram["mean"] is not None) else None
        print(f"{phase:<12} {f(cpu['min']):>8} {f(cpu['max']):>9} {f(cpu['mean']):>9} "
              f"{f(ram['min']):>9} {f(ram['max']):>9} {f(ram['mean']):>9} {f(dram):>9}")

    if baseline_ram is not None:
        print(f"\n  Baseline RAM host (mean): {baseline_ram:.1f} MB")
        print(f"  ΔRAM = kenaikan RAM host fase tsb terhadap baseline idle.")


def save_json(results: dict, raw: dict, baseline_ram: float | None, output_path: str):
    out = {
        "timestamp":         datetime.now().isoformat(),
        "sample_interval_s": SAMPLE_INTERVAL,
        "baseline_ram_mb":   baseline_ram,
        "summary":           results,
        "raw_samples":       raw,
    }
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    log(f"Hasil disimpan ke {output_path}")


# Main

def main():
    global BACKEND_URL, SAMPLE_INTERVAL

    parser = argparse.ArgumentParser(description="Proxmox Host Resource Monitor (per fase)")
    parser.add_argument("--backend",          default="http://localhost:8000/api/v1")
    parser.add_argument("--level-id",         type=int, default=2)
    parser.add_argument("--team",             default="testteam-A")
    parser.add_argument("--measure-prepare",  action="store_true",
                        help="Ukur fase prepare sebelum deploy/terminate")
    parser.add_argument("--baseline-seconds", type=int, default=10,
                        help="Durasi sampling baseline idle (default: 10 dtk)")
    parser.add_argument("--interval",         type=int, default=SAMPLE_INTERVAL,
                        help=f"Interval sampling host (default: {SAMPLE_INTERVAL} dtk)")
    parser.add_argument("--output",           default=None,
                        help="Path output JSON (default: tests/results/pve_<timestamp>.json)")
    args = parser.parse_args()

    SAMPLE_INTERVAL = args.interval
    BACKEND_URL = args.backend.rstrip("/")

    if args.output:
        output_path = args.output
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(RESULTS_DIR, f"pve_{ts}.json")

    # Konek ke host Proxmox
    try:
        proxmox, node = get_proxmox()
    except Exception as e:
        print(f"[ERROR] Tidak bisa konek ke Proxmox: {e}")
        return
    log(f"Terhubung ke host Proxmox: node='{node}'")

    monitor = HostMonitor(proxmox, node)
    results: dict = {}
    raw: dict = {}
    baseline_ram: float | None = None

    try:
        # 1. Baseline idle
        samples = measure_baseline(monitor, args.baseline_seconds)
        results["baseline"] = summarize(samples)
        raw["baseline"]     = samples
        baseline_ram = results["baseline"]["ram_used_mb"]["mean"]
        time.sleep(PAUSE_BETWEEN)

        # 2. Prepare (opsional)
        if args.measure_prepare:
            samples = measure_prepare(args.level_id, monitor)
            results["prepare"] = summarize(samples)
            raw["prepare"]     = samples
            time.sleep(PAUSE_BETWEEN)

        # 3. Deploy
        challenge_id, samples = measure_deploy(args.level_id, args.team, monitor)
        results["deploy"] = summarize(samples)
        raw["deploy"]     = samples
        time.sleep(PAUSE_BETWEEN)

        # 4. Terminate
        samples = measure_terminate(challenge_id, monitor)
        results["terminate"] = summarize(samples)
        raw["terminate"]     = samples

    except Exception as e:
        log(f"[ERROR] {e}")
        monitor.stop()

    if results:
        print_summary(results, baseline_ram)
        save_json(results, raw, baseline_ram, output_path)


if __name__ == "__main__":
    main()
