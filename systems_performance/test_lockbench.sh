#!/usr/bin/env bash

# Functional test for lockbench.c

set -euo pipefail

SRC=${1:-lockbench.c}
BIN=${2:-./lockbench}

if [[ "$BIN" != */* ]]; then
    BIN="./$BIN"
fi

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

pass() {
    printf 'PASS  %s\n' "$1"
}

fail() {
    printf 'FAIL  %s\n' "$1" >&2
    exit 1
}

expand_cpulist() {
    local list=$1 part start end i
    IFS=',' read -ra parts <<< "$list"

    for part in "${parts[@]}"; do
        if [[ $part == *-* ]]; then
            start=${part%-*}
            end=${part#*-}

            for ((i=start; i<=end; i++)); do
                printf '%s\n' "$i"
            done
        else
            printf '%s\n' "$part"
        fi
    done
}

[[ $(uname -s) == Linux ]] || fail "Linux is required"
[[ -f $SRC ]] || fail "Source file not found: $SRC"
command -v gcc >/dev/null 2>&1 || fail "gcc not found"

ALLOWED=$(awk '/^Cpus_allowed_list:/ {print $2}' /proc/self/status)
mapfile -t CPUS < <(expand_cpulist "$ALLOWED")

[[ ${#CPUS[@]} -ge 1 ]] || fail "Could not find an allowed CPU"

CPU0=${CPUS[0]}
CPU1=${CPUS[1]:-}

printf 'Using CPU(s): %s%s\n' "$CPU0" "${CPU1:+,$CPU1}"

gcc -O2 -Wall -Wextra -pthread -o "$BIN" "$SRC"
pass "Benchmark compiled"

# Check invalid CPU configuration
if "$BIN" --lock mutex --threads 1 --cs-ns 200 --samples 1000 --warmup 10 >/dev/null 2>&1; then
    fail "Missing --cpus was accepted"
fi

if "$BIN" --lock mutex --threads 1 --cpus "$CPU0,$CPU0" --cs-ns 200 --samples 1000 --warmup 10 >/dev/null 2>&1; then
    fail "Duplicate CPU list was accepted"
fi

pass "Invalid CPU configurations rejected"

# Test all lock types
for LOCK in spin mutex adaptive; do
    OUT="$TMP/${LOCK}.txt"
    CSV="$TMP/${LOCK}.csv"

    "$BIN" --lock "$LOCK" --threads 1 --cpus "$CPU0" --cs-ns 200 --samples 2000 --warmup 100 --csv "$CSV" >"$OUT" 2>&1

    grep -q "# calibration CPU: $CPU0" "$OUT" || fail "$LOCK calibration CPU incorrect"
    grep -q '^p50=' "$OUT" || fail "$LOCK latency output missing"
    grep -q '# realised critical-section length:' "$OUT" || fail "$LOCK realised CS missing"
    grep -q '# plausibility throughput:' "$OUT" || fail "$LOCK throughput missing"
    grep -q "# thread 0: cpu=$CPU0 acquisitions=2000 voluntary_ctxsw=.* involuntary_ctxsw=" "$OUT" || fail "$LOCK worker output incorrect"

    [[ $(wc -l < "$CSV") -eq 2001 ]] || fail "$LOCK CSV row count incorrect"
    [[ $(head -1 "$CSV") == 'lock,threads,cs_ns,cs_realised_ns,thread_id,cpu_id,sample_idx,latency_ns' ]] || fail "$LOCK CSV header incorrect"

    awk -F, -v lock="$LOCK" -v cpu="$CPU0" 'NR>1 && ($1!=lock || $2!=1 || $5!=0 || $6!=cpu) {exit 1}' "$CSV" || fail "$LOCK CSV data incorrect"
done

pass "All lock types passed"

# Test multiple workers if two CPUs are available
if [[ -n $CPU1 ]]; then
    OUT="$TMP/calibration_cpu.txt"

    "$BIN" --lock mutex --threads 2 --cpus "$CPU1,$CPU0" --cs-ns 200 --samples 1000 --warmup 50 >"$OUT" 2>&1

    grep -q "# calibration CPU: $CPU1" "$OUT" || fail "Calibration did not use the first CPU"
    pass "Calibration CPU correct"

    OUT="$TMP/split.txt"
    CSV="$TMP/split.csv"

    "$BIN" --lock mutex --threads 2 --cpus "$CPU0,$CPU1" --cs-ns 200 --samples 1001 --warmup 50 --csv "$CSV" >"$OUT" 2>&1

    grep -q "# thread 0: cpu=$CPU0 acquisitions=501 " "$OUT" || fail "Worker 0 sample count incorrect"
    grep -q "# thread 1: cpu=$CPU1 acquisitions=500 " "$OUT" || fail "Worker 1 sample count incorrect"

    [[ $(wc -l < "$CSV") -eq 1002 ]] || fail "Two-worker CSV row count incorrect"
    [[ $(awk -F, 'NR>1 && $5==0 {n++} END {print n+0}' "$CSV") -eq 501 ]] || fail "Worker 0 CSV count incorrect"
    [[ $(awk -F, 'NR>1 && $5==1 {n++} END {print n+0}' "$CSV") -eq 500 ]] || fail "Worker 1 CSV count incorrect"

    pass "Samples split correctly"

    # Test oversubscription mapping
    OUT="$TMP/oversub.txt"

    "$BIN" --lock mutex --threads 4 --cpus "$CPU0,$CPU1" --cs-ns 100 --samples 1000 --warmup 20 >"$OUT" 2>&1

    grep -q 'oversubscribed' "$OUT" || fail "Oversubscription warning missing"
    grep -q "# thread 0: cpu=$CPU0 " "$OUT" || fail "Thread 0 CPU incorrect"
    grep -q "# thread 1: cpu=$CPU1 " "$OUT" || fail "Thread 1 CPU incorrect"
    grep -q "# thread 2: cpu=$CPU0 " "$OUT" || fail "Thread 2 CPU incorrect"
    grep -q "# thread 3: cpu=$CPU1 " "$OUT" || fail "Thread 3 CPU incorrect"

    pass "Oversubscription mapping correct"
else
    printf 'SKIP  Multi-worker tests (only one CPU available)\n'
fi

printf '\nAll lockbench tests passed.\n'
