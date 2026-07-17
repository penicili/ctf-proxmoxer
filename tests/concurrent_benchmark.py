"""
concurrent_benchmark.py — Uji latency degradation & resource utilization saat
batch provisioning (deploy N tim dalam satu request: 5, 10, 20, dst).

Melengkapi monitor_pve.py (yang mengukur resource per FASE pada satu deploy)
dengan sudut pandang BEBAN BATCH: bagaimana latency per-deploy dan CPU/RAM
host berubah ketika ukuran batch meningkat, dibanding baseline N=1.
HostMonitor & get_proxmox() di bawah adalah komponen yang sama dengan
monitor_pve.py (proxmoxer → nodes(node).status, tanpa SSH).

Untuk tiap level N di --levels:
    1. Deploy N tim dalam SATU POST dengan team_names. Backend mereservasi VMID
       secara berurutan dan menjalankan background task secara terkendali untuk
       mencegah resource exhaustion pada Proxmox dan Ansible.
    2. Monitor CPU/RAM host Proxmox selama fase deploy & terminate berlangsung.
    3. Catat latency tiap tim individual (deploy_server, terminate_server) dan
       makespan batch (dari submit pertama sampai SEMUA tim selesai).
    4. Terminate N tim itu sekaligus, monitor resource lagi.

Di akhir: tabel LATENCY DEGRADATION (mean latency tiap level vs baseline N
terkecil, dalam % kenaikan) + tabel resource utilization per level.

Penggunaan:
    # Sweep batch 1, 5, 10, 20 (default), 1 putaran tiap level:
    python tests/concurrent_benchmark.py --level-id 1

    # Replikasi opsional (hanya jika kapasitas infrastruktur mencukupi):
    python tests/concurrent_benchmark.py --level-id 1 --levels 1,5,10,20 --rounds 3

    # Tanpa monitoring resource host (kalau proxmoxer/koneksi tak tersedia):
    python tests/concurrent_benchmark.py --level-id 1 --no-resource-monitor

    # Label run + custom prefix nama tim:
    python tests/concurrent_benchmark.py --level-id 1 --label "concurrent-sweep" --team-prefix load
"""

import argparse
import csv
import json
import os
import re
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import requests

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# Config

BACKEND_URL     = "http://localhost:8000/api/v1"
SAMPLE_INTERVAL = 2      # detik antar sampel CPU/RAM host
POLL_INTERVAL   = 15     # detik antar polling status deployment
TIMEOUT         = 600    # timeout default, dipakai untuk fase terminate
INITIAL_POLL_DELAY = 120 # jangan poll deploy sebelum dua menit
PAUSE_BETWEEN   = 5      # detik jeda antar fase / round / level
REQ_TIMEOUT     = (5, 30)

RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")

_log_lock = threading.Lock()


# Helpers

def log(msg: str):
    with _log_lock:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def slugify(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", text).strip("-").lower()

def dt_diff(start_str, end_str):
    if not start_str or not end_str:
        return None
    def parse(s):
        return datetime.fromisoformat(s.rstrip("Z")).replace(tzinfo=timezone.utc)
    return round((parse(end_str) - parse(start_str)).total_seconds(), 2)

def poll_challenge(
    challenge_id: int,
    target_status: str,
    *,
    initial_delay: int = 0,
    timeout: int = TIMEOUT,
) -> dict:
    if initial_delay:
        log(f"  challenge {challenge_id} → mulai polling dalam {initial_delay}s")
        time.sleep(initial_delay)
    # Timeout dihitung setelah polling dimulai. Dengan begitu item di belakang
    # antrean memperoleh jendela observasi penuh yang sama dengan item pertama.
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            resp = requests.get(f"{BACKEND_URL}/challenges/{challenge_id}", timeout=REQ_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            log(f"  challenge {challenge_id} → (backend sibuk, retry: {type(e).__name__})")
            time.sleep(POLL_INTERVAL)
            continue
        status = data.get("deployment_status", "")
        if status == target_status:
            return data
        if status == "error":
            raise RuntimeError(f"Challenge {challenge_id} error: {data.get('error_message')}")
        time.sleep(POLL_INTERVAL)
    raise TimeoutError(f"Timeout menunggu status '{target_status}' pada challenge {challenge_id}")

def find_existing_batch(level_id: int, teams: list[str]) -> dict[str, int]:
    """Pulihkan challenge ID bila respons batch sudah hilang di sisi klien."""
    found: dict[str, int] = {}
    try:
        for team in teams:
            resp = requests.get(
                f"{BACKEND_URL}/challenges",
                params={"team": team},
                timeout=REQ_TIMEOUT,
            )
            resp.raise_for_status()
            challenge = next(
                (item for item in resp.json().get("challenges", [])
                 if item.get("level_id") == level_id),
                None,
            )
            if challenge and challenge.get("id"):
                found[team] = challenge["id"]
    except requests.RequestException:
        return {}
    return found


def deploy_batch(level_id: int, teams: list[str]) -> dict[str, int]:
    """Kirim satu batch sesuai kontrak API dan kembalikan challenge ID per tim."""
    last_err = None
    for attempt in range(5):
        try:
            resp = requests.post(f"{BACKEND_URL}/challenges", json={
                "level_id":   level_id,
                "team_names": teams,
            }, timeout=REQ_TIMEOUT)
            if resp.status_code == 409:
                recovered = find_existing_batch(level_id, teams)
                if len(recovered) == len(teams):
                    log("  POST batch konflik setelah retry; memakai deployment yang sudah tercatat")
                    return recovered
            resp.raise_for_status()
            results = resp.json().get("results", [])
            challenge_ids = {
                result["team"]: result["challenge_id"]
                for result in results
                if not result.get("skipped") and result.get("challenge_id")
            }
            missing = [team for team in teams if team not in challenge_ids]
            if missing:
                raise RuntimeError(f"Batch deploy tidak membuat challenge untuk: {missing}")
            return challenge_ids
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            last_err = e
            recovered = find_existing_batch(level_id, teams)
            if len(recovered) == len(teams):
                log("  POST batch timeout; memakai deployment yang sudah tercatat")
                return recovered
            log(f"  POST batch timeout (attempt {attempt+1}/5), retry...")
            time.sleep(POLL_INTERVAL)
    else:
        raise RuntimeError(f"POST /challenges batch gagal setelah 5x retry: {last_err}")


def get_proxmox():
    """Reuse koneksi & node dari ProxmoxService (tanpa SSH) — sama seperti monitor_pve.py."""
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from config.settings import settings
    from services.proxmox_service import ProxmoxService

    svc = ProxmoxService(settings)
    proxmox = svc._ensure_connected()
    if proxmox is None:
        raise RuntimeError("Gagal konek ke Proxmox (cek PROXMOX_HOST/USER/PASSWORD di settings).")
    return proxmox, svc.node, svc


# Host Resource Monitor (identik dengan monitor_pve.py)

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
                cpu = float(st.get("cpu", 0)) * 100
                mem = st.get("memory", {}) or {}
                used_mb  = float(mem.get("used", 0))  / (1024 * 1024)
                total_mb = float(mem.get("total", 0)) / (1024 * 1024)
                self.samples.append({
                    "cpu_pct":      round(cpu, 1),
                    "ram_used_mb":  round(used_mb, 1),
                    "ram_total_mb": round(total_mb, 1),
                })
            except Exception as e:
                log(f"  [WARN] gagal baca status host: {e}")
            time.sleep(SAMPLE_INTERVAL)


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

def summarize_resource(samples: list) -> dict:
    if not samples:
        return {"n_samples": 0, "cpu_pct": _stats([]), "ram_used_mb": _stats([])}
    return {
        "n_samples":   len(samples),
        "cpu_pct":     _stats([s["cpu_pct"] for s in samples]),
        "ram_used_mb": _stats([s["ram_used_mb"] for s in samples]),
    }


# Observasi deploy dan terminasi per-tim

def wait_for_deploy(team: str, challenge_id: int, t0: float) -> dict:
    """Pantau satu item batch setelah jeda polling yang disengaja."""
    try:
        data = poll_challenge(
            challenge_id,
            "running",
            initial_delay=INITIAL_POLL_DELAY,
        )
        t1 = time.monotonic()
        return {
            "team":          team,
            "challenge_id":  challenge_id,
            "vm_id":         data.get("vm_id"),
            "started_at":    data.get("started_at"),
            "deploy_client": round(t1 - t0, 2),
            "deploy_server": dt_diff(data.get("created_at"), data.get("started_at")),
            "error":         None,
        }
    except Exception as e:
        # Deploy gagal (mis. 'start failed: got timeout') — VM bisa saja SUDAH
        # terlanjur dibuat di Proxmox sebelum gagal start. Coba tarik vm_id-nya
        # sekali lagi langsung dari backend supaya tetap ke-track buat cleanup,
        # bukan jadi orphan yang baru ketahuan lewat cleanup_orphan_vms.py nanti.
        vm_id = None
        if challenge_id:
            try:
                resp = requests.get(f"{BACKEND_URL}/challenges/{challenge_id}", timeout=REQ_TIMEOUT)
                if resp.ok:
                    vm_id = resp.json().get("vm_id")
            except Exception:
                pass
        return {"team": team, "challenge_id": challenge_id, "vm_id": vm_id, "error": str(e)}

def terminate_and_measure(deploy_result: dict) -> dict:
    challenge_id = deploy_result["challenge_id"]
    t0 = time.monotonic()
    try:
        resp = requests.delete(f"{BACKEND_URL}/challenges/{challenge_id}", timeout=REQ_TIMEOUT)
        resp.raise_for_status()
        data = poll_challenge(challenge_id, "terminated")
        t1 = time.monotonic()
        return {
            "team":             deploy_result["team"],
            "challenge_id":     challenge_id,
            "terminate_client": round(t1 - t0, 2),
            "terminate_server": dt_diff(deploy_result.get("started_at"), data.get("terminated_at")),
            "error":            None,
        }
    except Exception as e:
        return {"team": deploy_result["team"], "challenge_id": challenge_id, "error": str(e)}


# Satu round pada satu level N

def run_level_round(level_id: int, n: int, round_num: int, total_rounds: int,
                     team_prefix: str, monitor: "HostMonitor | None") -> dict:
    teams = [f"{team_prefix}-N{n}-r{round_num}-{i:02d}" for i in range(1, n + 1)]

    log(f"\n{'═'*56}")
    log(f"BATCH N={n} — round {round_num}/{total_rounds} ({n} tim, satu POST)")
    log(f"{'═'*56}")

    # ── Deploy satu batch N tim, monitor resource host selama fase ini ──
    if monitor:
        monitor.start()
    deploy_results = []
    t_start = time.monotonic()
    try:
        challenge_ids = deploy_batch(level_id, teams)
        # Polling dibuat berantai. Item berikutnya baru disentuh 120 detik
        # setelah item sebelumnya mencapai status terminal, sehingga backend
        # tidak dibebani polling untuk VM yang masih berada di antrean.
        for team in teams:
            deploy_results.append(wait_for_deploy(team, challenge_ids[team], t_start))
    except Exception as e:
        deploy_results = [
            {"team": team, "challenge_id": None, "vm_id": None, "error": str(e)}
            for team in teams
        ]
    makespan_deploy = round(time.monotonic() - t_start, 2)
    resource_deploy = summarize_resource(monitor.stop()) if monitor else None

    ok = [r for r in deploy_results if not r.get("error")]
    err = [r for r in deploy_results if r.get("error")]
    log(f"  DEPLOY selesai — makespan {makespan_deploy}s | sukses {len(ok)}/{n}")
    for r in err:
        log(f"  [ERROR] {r['team']}: {r['error']}")

    time.sleep(PAUSE_BETWEEN)

    # ── Terminate tim yang berhasil, paralel, monitor resource lagi ────
    term_results = []
    makespan_terminate = None
    resource_terminate = None
    # Hasil polling yang error tetap mungkin punya VM hidup; terminate semua
    # deployment yang sudah tercatat agar tidak meninggalkan orphan.
    cleanup_candidates = [r for r in deploy_results if r.get("challenge_id")]
    if cleanup_candidates:
        if monitor:
            monitor.start()
        t_start = time.monotonic()
        with ThreadPoolExecutor(max_workers=len(cleanup_candidates)) as executor:
            futures = [executor.submit(terminate_and_measure, r) for r in cleanup_candidates]
            for fut in as_completed(futures):
                term_results.append(fut.result())
        makespan_terminate = round(time.monotonic() - t_start, 2)
        resource_terminate = summarize_resource(monitor.stop()) if monitor else None
        ok_term = [r for r in term_results if not r.get("error")]
        log(f"  TERMINATE selesai — makespan {makespan_terminate}s | sukses {len(ok_term)}/{len(cleanup_candidates)}")

    return {
        "n":                  n,
        "round":              round_num,
        "deploy_results":     deploy_results,
        "terminate_results":  term_results,
        "makespan_deploy":    makespan_deploy,
        "makespan_terminate": makespan_terminate,
        "resource_deploy":    resource_deploy,
        "resource_terminate": resource_terminate,
    }


def measure_idle_baseline(monitor: "HostMonitor", seconds: int) -> dict:
    log(f"\n{'─'*50}\nBASELINE IDLE ({seconds}s) — sebelum sweep dimulai\n{'─'*50}")
    monitor.start()
    time.sleep(seconds)
    return summarize_resource(monitor.stop())


# Agregasi & pelaporan lintas-level

def aggregate_level(level_rounds: list) -> dict:
    """Gabungkan semua round pada satu level N jadi satu ringkasan."""
    all_deploy_ok  = [r for rd in level_rounds for r in rd["deploy_results"] if not r.get("error")]
    all_term_ok    = [r for rd in level_rounds for r in rd["terminate_results"] if not r.get("error")]
    n_attempted    = sum(rd["n"] for rd in level_rounds)

    deploy_lat = [r["deploy_server"] if r.get("deploy_server") is not None else r["deploy_client"]
                  for r in all_deploy_ok]
    term_lat   = [r["terminate_server"] if r.get("terminate_server") is not None else r["terminate_client"]
                  for r in all_term_ok]
    makespans_d = [rd["makespan_deploy"] for rd in level_rounds]
    makespans_t = [rd["makespan_terminate"] for rd in level_rounds if rd["makespan_terminate"] is not None]

    res_d = [rd["resource_deploy"] for rd in level_rounds if rd.get("resource_deploy")]
    res_t = [rd["resource_terminate"] for rd in level_rounds if rd.get("resource_terminate")]
    cpu_d_means = [r["cpu_pct"]["mean"] for r in res_d if r["cpu_pct"]["mean"] is not None]
    cpu_d_maxes = [r["cpu_pct"]["max"]  for r in res_d if r["cpu_pct"]["max"]  is not None]
    ram_d_means = [r["ram_used_mb"]["mean"] for r in res_d if r["ram_used_mb"]["mean"] is not None]
    ram_d_maxes = [r["ram_used_mb"]["max"]  for r in res_d if r["ram_used_mb"]["max"]  is not None]

    return {
        "n":                 level_rounds[0]["n"],
        "rounds":            len(level_rounds),
        "success_rate":      round(len(all_deploy_ok) / n_attempted * 100, 1) if n_attempted else None,
        "deploy_latency":    _stats(deploy_lat),
        "terminate_latency": _stats(term_lat),
        "makespan_deploy":   _stats(makespans_d),
        "makespan_terminate": _stats(makespans_t),
        "cpu_pct_mean_of_means": round(statistics.mean(cpu_d_means), 1) if cpu_d_means else None,
        "cpu_pct_max":           round(max(cpu_d_maxes), 1) if cpu_d_maxes else None,
        "ram_used_mb_mean_of_means": round(statistics.mean(ram_d_means), 1) if ram_d_means else None,
        "ram_used_mb_max":           round(max(ram_d_maxes), 1) if ram_d_maxes else None,
    }


def print_degradation_table(level_summaries: list, baseline_idle_ram: float | None):
    baseline = level_summaries[0]  # level terkecil (idealnya N=1)
    baseline_lat = baseline["deploy_latency"]["mean"]

    print(f"\n{'═'*88}")
    print("LATENCY DEGRADATION — batch deploy vs baseline N={}".format(baseline["n"]))
    print(f"{'═'*88}")
    print(f"{'N':>4} {'Sukses':>8} {'Latency mean':>13} {'Stdev':>8} {'Δ vs baseline':>14} {'Makespan mean':>14}")
    print(f"{'':>4} {'':>8} {'(s)':>13} {'(s)':>8} {'(%)':>14} {'(s)':>14}")
    print("─" * 88)
    for s in level_summaries:
        lat = s["deploy_latency"]["mean"]
        stdev = s["deploy_latency"]["stdev"]
        pct = round((lat - baseline_lat) / baseline_lat * 100, 1) if (lat is not None and baseline_lat) else None
        mk = s["makespan_deploy"]["mean"]
        print(f"{s['n']:>4} {s['success_rate']:>7}% {lat if lat is not None else '—':>13} "
              f"{stdev if stdev is not None else '—':>8} "
              f"{(f'+{pct}%' if pct and pct > 0 else f'{pct}%') if pct is not None else '—':>14} "
              f"{mk if mk is not None else '—':>14}")

    print(f"\n{'═'*88}")
    print("RESOURCE UTILIZATION — host Proxmox selama fase deploy")
    print(f"{'═'*88}")
    print(f"{'N':>4} {'CPU mean':>10} {'CPU max':>10} {'RAM mean':>11} {'RAM max':>11} {'ΔRAM vs idle':>14}")
    print(f"{'':>4} {'(%)':>10} {'(%)':>10} {'(MB)':>11} {'(MB)':>11} {'(MB)':>14}")
    print("─" * 88)
    for s in level_summaries:
        ram_mean = s["ram_used_mb_mean_of_means"]
        dram = round(ram_mean - baseline_idle_ram, 1) if (ram_mean is not None and baseline_idle_ram is not None) else None
        print(f"{s['n']:>4} {s['cpu_pct_mean_of_means'] if s['cpu_pct_mean_of_means'] is not None else '—':>10} "
              f"{s['cpu_pct_max'] if s['cpu_pct_max'] is not None else '—':>10} "
              f"{ram_mean if ram_mean is not None else '—':>11} "
              f"{s['ram_used_mb_max'] if s['ram_used_mb_max'] is not None else '—':>11} "
              f"{dram if dram is not None else '—':>14}")

    if baseline_idle_ram is not None:
        print(f"\n  Baseline RAM host idle (mean): {baseline_idle_ram:.1f} MB")


def save_csv(level_summaries: list, output_path: str):
    """CSV siap-tempel untuk tabel di paper (Excel/LaTeX-friendly)."""
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "N", "success_rate_pct", "deploy_latency_mean_s", "deploy_latency_stdev_s",
            "degradation_pct", "makespan_deploy_mean_s", "terminate_latency_mean_s",
            "makespan_terminate_mean_s", "cpu_pct_mean", "cpu_pct_max",
            "ram_used_mb_mean", "ram_used_mb_max",
        ])
        baseline_lat = level_summaries[0]["deploy_latency"]["mean"]
        for s in level_summaries:
            lat = s["deploy_latency"]["mean"]
            pct = round((lat - baseline_lat) / baseline_lat * 100, 1) if (lat is not None and baseline_lat) else None
            writer.writerow([
                s["n"], s["success_rate"], lat, s["deploy_latency"]["stdev"], pct,
                s["makespan_deploy"]["mean"], s["terminate_latency"]["mean"],
                s["makespan_terminate"]["mean"], s["cpu_pct_mean_of_means"], s["cpu_pct_max"],
                s["ram_used_mb_mean_of_means"], s["ram_used_mb_max"],
            ])
    log(f"Tabel CSV disimpan ke {output_path}")


def save_json(all_rounds: list, level_summaries: list, baseline_idle_ram, output_path: str, label, meta):
    out = {
        "timestamp":         datetime.now().isoformat(),
        "label":             label,
        "meta":              meta,
        "baseline_idle_ram_mb": baseline_idle_ram,
        "level_summaries":   level_summaries,
        "raw_rounds":        all_rounds,
    }
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=str)
    log(f"Hasil lengkap disimpan ke {output_path}")


# Cleanup VM (sama seperti benchmark.py)

def destroy_vms(vmids: list) -> None:
    vmids = [v for v in vmids if v]
    if not vmids:
        log("Tidak ada VMID untuk di-destroy.")
        return
    log(f"\n{'═'*52}\nCLEANUP — qm destroy {len(vmids)} VM: {vmids}\n{'═'*52}")
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from config.settings import settings
        from services.proxmox_service import ProxmoxService
    except Exception as e:
        log(f"[WARN] Gagal import ProxmoxService: {e}")
        log(f"  Destroy manual di PVE: qm destroy {' '.join(str(v) for v in vmids)} --purge")
        return
    svc = ProxmoxService(settings)
    for vmid in vmids:
        try:
            svc.destroy_vm(vmid)
            log(f"  ✓ VM {vmid} destroyed")
        except Exception as e:
            log(f"  ✗ VM {vmid} gagal di-destroy: {e}")


# Main

def main():
    global BACKEND_URL, SAMPLE_INTERVAL

    parser = argparse.ArgumentParser(description="Concurrent Provisioning: Latency Degradation & Resource Utilization")
    parser.add_argument("--backend",     default="http://localhost:8000/api/v1")
    parser.add_argument("--level-id",    type=int, default=2, help="ID level challenge yang sudah ready")
    parser.add_argument("--levels",      default="1,5,10,20", help="Daftar ukuran batch N, dipisah koma (default: 1,5,10,20 — 1=baseline)")
    parser.add_argument("--rounds",      type=int, default=1, help="Jumlah putaran tiap level (default: 1)")
    parser.add_argument("--team-prefix", default="load", help="Prefix nama tim (default: load)")
    parser.add_argument("--label",       default=None)
    parser.add_argument("--output",      default=None, help="Path JSON output (default: tests/results/<ts>_degradation[_label].json)")
    parser.add_argument("--interval",    type=int, default=SAMPLE_INTERVAL, help="Interval sampling resource host (dtk)")
    parser.add_argument("--baseline-seconds", type=int, default=10, help="Durasi baseline idle host sebelum sweep (dtk)")
    parser.add_argument("--no-resource-monitor", action="store_true", help="Lewati monitoring CPU/RAM host Proxmox")
    parser.add_argument("--keep-vms",    action="store_true")
    args = parser.parse_args()

    BACKEND_URL = args.backend.rstrip("/")
    SAMPLE_INTERVAL = args.interval
    levels = sorted(int(x.strip()) for x in args.levels.split(",") if x.strip())

    if args.output:
        output_path = args.output
        csv_path = os.path.splitext(output_path)[0] + ".csv"
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = f"_{slugify(args.label)}" if args.label else ""
        output_path = os.path.join(RESULTS_DIR, f"{ts}_degradation{suffix}.json")
        csv_path = os.path.join(RESULTS_DIR, f"{ts}_degradation{suffix}.csv")

    # Setup resource monitor (opsional)
    monitor = None
    baseline_idle_ram = None
    if not args.no_resource_monitor:
        try:
            proxmox, node, _svc = get_proxmox()
            log(f"Terhubung ke host Proxmox: node='{node}'")
            monitor = HostMonitor(proxmox, node)
            baseline_idle_ram = measure_idle_baseline(monitor, args.baseline_seconds)["ram_used_mb"]["mean"]
            time.sleep(PAUSE_BETWEEN)
        except Exception as e:
            log(f"[WARN] Resource monitoring dinonaktifkan (gagal konek Proxmox): {e}")
            monitor = None

    # Sweep tiap level N — VM di-destroy SEGERA setelah tiap level selesai
    # (bukan ditumpuk sampai akhir sweep), dan kalau di-interrupt (Ctrl+C)
    # tetap coba destroy VM yang sudah sempat dibuat sejauh itu di blok finally.
    all_rounds = []
    level_summaries = []
    interrupted = False
    try:
        for n in levels:
            level_rounds = []
            for rnum in range(1, args.rounds + 1):
                rd = run_level_round(args.level_id, n, rnum, args.rounds, args.team_prefix, monitor)
                level_rounds.append(rd)
                all_rounds.append(rd)
                time.sleep(PAUSE_BETWEEN)
            level_summaries.append(aggregate_level(level_rounds))

            # Cleanup langsung untuk level N ini, sebelum lanjut ke level berikutnya.
            level_vmids = [r.get("vm_id") for rd in level_rounds for r in rd["deploy_results"] if r.get("vm_id")]
            if not args.keep_vms:
                log(f"\nLevel N={n} selesai — cleanup {len(level_vmids)} VM level ini sebelum lanjut...")
                destroy_vms(level_vmids)
            else:
                log(f"--keep-vms aktif, {len(level_vmids)} VM level N={n} TIDAK di-destroy: {level_vmids}")

            time.sleep(PAUSE_BETWEEN)

    except KeyboardInterrupt:
        interrupted = True
        log("\n[INTERRUPTED] Ctrl+C diterima — menghentikan sweep, cleanup VM yang sudah dibuat sejauh ini...")
    finally:
        # Safety net: level yang sedang berjalan saat interrupt belum sempat
        # masuk 'level_summaries' / cleanup di atas, jadi sisir ulang semua VM
        # dari all_rounds yang terkumpul sejauh ini (termasuk deploy yang gagal,
            # karena vm_id-nya sudah ditangkap juga oleh wait_for_deploy).
        if not args.keep_vms:
            remaining_vmids = [r.get("vm_id") for rd in all_rounds for r in rd["deploy_results"] if r.get("vm_id")]
            if remaining_vmids:
                log(f"Cleanup akhir (safety net) — {len(remaining_vmids)} VM dari seluruh round yang tercatat...")
                destroy_vms(remaining_vmids)
        if interrupted:
            log("Catatan: kalau ada thread deploy yang lagi jalan PAS interrupt terjadi,")
            log("VM-nya bisa jadi belum sempat tercatat di sini (belum balik dari poll_challenge).")
            log("Jalankan tests/cleanup_orphan_vms.py --start <awal> --end <akhir> untuk sapu bersih orphan.")

    if level_summaries:
        print_degradation_table(level_summaries, baseline_idle_ram)

        meta = {
            "backend": BACKEND_URL, "level_id": args.level_id,
            "levels": levels, "rounds_per_level": args.rounds,
            "team_prefix": args.team_prefix, "resource_monitor": monitor is not None,
            "interrupted": interrupted,
        }
        save_json(all_rounds, level_summaries, baseline_idle_ram, output_path, args.label, meta)
        save_csv(level_summaries, csv_path)
    else:
        log("Tidak ada level yang selesai sebelum interrupt — tidak ada hasil untuk disimpan.")


if __name__ == "__main__":
    main()
