#!/usr/bin/env bash
#
# monitor_pve.sh — Pantau sumber daya HOST Proxmox (NF-2 aspek b).
#
# Dijalankan LANGSUNG DI PVE HOST (bukan di mesin backend), karena mengukur
# biaya nyata menjalankan VM challenge: RAM/CPU host + RAM teralokasi per VM.
# Tanpa dependensi tambahan — cukup `free`, `qm`, dan /proc/stat.
#
# Cara pakai (di PVE, sebagai root):
#   chmod +x monitor_pve.sh
#   ./monitor_pve.sh                 # interval 5 dtk, log ke ~/pve_monitor_<ts>.log
#   ./monitor_pve.sh -i 3 -o run.log # interval 3 dtk, file output custom
#
# Alur uji:
#   1. Jalankan skrip ini DULU (mencatat baseline idle otomatis).
#   2. Dari platform, deploy challenge BERTAHAP: 1 -> 3 -> 5.
#      Beri jeda ~30-60 dtk tiap tingkat agar angka steady.
#   3. Tekan Ctrl-C untuk berhenti -> skrip cetak ringkasan + simpan log.
#
set -u

INTERVAL=5
OUTPUT=""

while getopts "i:o:h" opt; do
  case "$opt" in
    i) INTERVAL="$OPTARG" ;;
    o) OUTPUT="$OPTARG" ;;
    h) grep '^#' "$0" | sed 's/^# \?//'; exit 0 ;;
    *) echo "Opsi tidak dikenal. -h untuk bantuan." >&2; exit 1 ;;
  esac
done

[ -z "$OUTPUT" ] && OUTPUT="$HOME/pve_monitor_$(date +%Y%m%d_%H%M%S).log"

# --- Helper: baca CPU jiffies dari /proc/stat (baris agregat 'cpu ') ---
read_cpu() {
  read -r _ u n s idle iow irq sirq steal _ < /proc/stat
  local total=$((u + n + s + idle + iow + irq + sirq + steal))
  local busy=$((total - idle - iow))
  echo "$total $busy"
}

# CPU% antara dua titik waktu (butuh sampel sebelumnya)
PREV_TOTAL=0; PREV_BUSY=0
cpu_pct() {
  local now total busy dtot dbusy
  now=$(read_cpu); total=${now%% *}; busy=${now##* }
  dtot=$((total - PREV_TOTAL)); dbusy=$((busy - PREV_BUSY))
  PREV_TOTAL=$total; PREV_BUSY=$busy
  if [ "$dtot" -gt 0 ]; then
    awk "BEGIN { printf \"%.1f\", $dbusy/$dtot*100 }"
  else
    echo "0.0"
  fi
}

# RAM host (MB): total, used (=total-available), available
mem_line() {
  free -m | awk '/^Mem:/ { print $2, $2-$7, $7 }'  # total used_real avail
}

# VM running: jumlah + total RAM teralokasi (MB) + daftar vmid
vm_stats() {
  # qm list: VMID NAME STATUS MEM(MB) BOOTDISK PID  (header dilewati)
  qm list 2>/dev/null | awk 'NR>1 && $3=="running" {
    cnt++; mem+=$4; ids = ids (ids?",":"") $1
  } END { printf "%d %d %s", cnt+0, mem+0, (ids==""?"-":ids) }'
}

log() { echo "$@" | tee -a "$OUTPUT"; }

# --- Header + baseline ---
{
  echo "================================================================"
  echo " MONITORING SUMBER DAYA HOST PROXMOX (NF-2)"
  echo " Host    : $(hostname)   Tanggal: $(date '+%Y-%m-%d %H:%M:%S')"
  echo " Interval: ${INTERVAL}s   Output : $OUTPUT"
  echo "================================================================"
  echo ""
  echo " BASELINE (kondisi saat skrip dimulai):"
  read -r BT BU BA <<< "$(mem_line)"
  echo "   RAM total   : ${BT} MB"
  echo "   RAM used    : ${BU} MB"
  echo "   RAM avail   : ${BA} MB"
  read -r BVC BVM BVIDS <<< "$(vm_stats)"
  echo "   VM running  : ${BVC} (RAM teralokasi ${BVM} MB) [${BVIDS}]"
  echo ""
  printf " %-19s %8s %9s %9s %7s %6s %9s %s\n" \
    "waktu" "RAM_used" "RAM_avail" "RAM_used%" "CPU%" "nVM" "VMram_MB" "vmids"
  echo " ---------------------------------------------------------------------------------------"
} | tee "$OUTPUT"

# Warm-up CPU (sampel pertama dibuang agar delta valid)
now=$(read_cpu); PREV_TOTAL=${now%% *}; PREV_BUSY=${now##* }
sleep 1

# --- Ringkasan saat Ctrl-C ---
MAX_VM=0; MAX_USED=0
summary() {
  echo ""
  log "================================================================"
  log " RINGKASAN"
  log "   Baseline RAM used   : ${BU} MB (avail ${BA} MB)"
  log "   Puncak RAM used     : ${MAX_USED} MB"
  log "   Delta RAM (puncak-baseline): $((MAX_USED - BU)) MB"
  log "   Puncak VM running   : ${MAX_VM}"
  if [ "$MAX_VM" -gt 0 ]; then
    local per=$(( (MAX_USED - BU) / MAX_VM ))
    log "   ~RAM per challenge  : ${per} MB (rata-rata)"
    if [ "$per" -gt 0 ]; then
      log "   Estimasi kapasitas  : ~$(( BA / per )) challenge (avail baseline / RAM per challenge)"
    fi
  fi
  log "   Log lengkap         : $OUTPUT"
  log "================================================================"
  exit 0
}
trap summary INT TERM

# --- Loop sampling ---
while true; do
  read -r MT MU MA <<< "$(mem_line)"
  CP=$(cpu_pct)
  read -r VC VM VIDS <<< "$(vm_stats)"
  USEDPCT=$(awk "BEGIN { printf \"%.1f\", $MU/$MT*100 }")

  [ "$MU" -gt "$MAX_USED" ] && MAX_USED=$MU
  [ "$VC" -gt "$MAX_VM" ]   && MAX_VM=$VC

  printf " %-19s %7d %8d %8s %6s %5d %8d %s\n" \
    "$(date '+%Y-%m-%d %H:%M:%S')" "$MU" "$MA" "$USEDPCT" "$CP" "$VC" "$VM" "$VIDS" \
    | tee -a "$OUTPUT"

  sleep "$INTERVAL"
done
