#!/usr/bin/env bash

# Run the pilot and choose the critical-section length

set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG="$ROOT/config/experiment.conf"
OUT="$ROOT/results/pilot"
BENCH="$ROOT/lockbench"

if [ ! -f "$CONFIG" ]; then
    printf 'Experiment configuration not found.\n'
    exit 1
fi

source "$CONFIG"

if [ -z "$CPU_LIST" ] || [ -z "$PHYSICAL_CORES" ]; then
    printf 'CPU_LIST or PHYSICAL_CORES is not configured.\n'
    printf 'Run scripts/configure_experiment.sh first.\n'
    exit 1
fi

if [ "$PHYSICAL_CORES" -lt 2 ]; then
    printf 'At least two measurement cores are needed for the pilot.\n'
    exit 1
fi

mkdir -p "$OUT"

# Compile the benchmark
if ! gcc -O2 -Wall -Wextra -pthread -o "$BENCH" "$ROOT/lockbench.c"; then
    printf 'Benchmark compilation failed.\n'
    exit 1
fi

printf 'Benchmark compiled.\n'

# Use the first two measurement CPUs
IFS=',' read -ra CPU_ARRAY <<< "$CPU_LIST"
CPU1="${CPU_ARRAY[0]}"
CPU2="${CPU_ARRAY[1]}"
PILOT_CPUS="$CPU1,$CPU2"

printf '\nLock Contention EVA - Pilot\n'
printf 'Pilot CPUs: %s\n' "$PILOT_CPUS"
printf 'Candidate CS values: %s\n' "$CS_CANDIDATES"
printf 'Samples per run: %s\n' "$TOTAL_SAMPLES"

SUMMARY="$OUT/pilot_summary.csv"
printf 'cs_target_ns,lock,cs_realised_ns,timer_overhead_ns\n' > "$SUMMARY"

SELECTED_CS=""

# Test each candidate until one passes
for cs in $CS_CANDIDATES; do
    printf '\nTesting CS: %sns\n' "$cs"

    valid=1
    max_timer=0
    lower=$((cs * 80 / 100))
    upper=$((cs * 120 / 100))

    for lock in $LOCKS; do
        PREFIX="$OUT/cs_${cs}_${lock}"

        if ! "$BENCH" --lock "$lock" --threads 2 --cpus "$PILOT_CPUS" --cs-ns "$cs" --samples "$TOTAL_SAMPLES" --warmup "$WARMUP" --csv "${PREFIX}.csv" > "${PREFIX}.txt" 2>&1; then
            printf 'FAIL %s at CS=%sns\n' "$lock" "$cs"
            exit 1
        fi

        realised="$(grep '^# cs:' "${PREFIX}.txt" | sed -n 's/.*realised≈\([0-9]*\)ns.*/\1/p')"
        timer="$(grep '^# timer:' "${PREFIX}.txt" | sed -n 's/.*overhead≈\([0-9]*\)ns.*/\1/p')"

        if [ -z "$realised" ] || [ -z "$timer" ]; then
            printf 'FAIL Could not read results for %s at CS=%sns\n' "$lock" "$cs"
            exit 1
        fi

        printf '%s,%s,%s,%s\n' "$cs" "$lock" "$realised" "$timer" >> "$SUMMARY"
        printf '  %s: realised=%sns timer=%sns\n' "$lock" "$realised" "$timer"

        if [ "$realised" -lt "$lower" ] || [ "$realised" -gt "$upper" ]; then
            valid=0
        fi

        if [ "$timer" -gt "$max_timer" ]; then
            max_timer="$timer"
        fi
    done

    if [ "$cs" -lt $((max_timer * 5)) ]; then
        valid=0
    fi

    if [ "$valid" -eq 1 ]; then
        SELECTED_CS="$cs"
        break
    fi
done

printf '\nPilot summary:\n'
cat "$SUMMARY"

if [ -z "$SELECTED_CS" ]; then
    printf '\nNo candidate CS passed the checks.\n'
    exit 1
fi

printf '\nSelected CS: %sns\n' "$SELECTED_CS"

# Save the selected CS
sed -i "s/^CS_NS=.*/CS_NS=\"$SELECTED_CS\"/" "$CONFIG"
printf 'Updated experiment.conf with CS_NS=%s\n' "$SELECTED_CS"

# Run the N=1 sanity check
printf '\nRunning N=1 sanity check...\n'

for lock in $LOCKS; do
    PREFIX="$OUT/h1_${lock}"

    if ! "$BENCH" --lock "$lock" --threads 1 --cpus "$CPU1" --cs-ns "$SELECTED_CS" --samples "$TOTAL_SAMPLES" --warmup "$WARMUP" --csv "${PREFIX}.csv" > "${PREFIX}.txt" 2>&1; then
        printf 'FAIL N=1 %s run failed.\n' "$lock"
        exit 1
    fi

    p50="$(grep '^p50=' "${PREFIX}.txt" | sed -n 's/p50=\([0-9]*\).*/\1/p')"
    p99="$(grep '^p50=' "${PREFIX}.txt" | sed -n 's/.*p99=\([0-9]*\).*/\1/p')"

    if [ -z "$p50" ] || [ -z "$p99" ]; then
        printf 'FAIL Could not read N=1 results for %s.\n' "$lock"
        exit 1
    fi

    printf '  %s: p50=%sns p99=%sns\n' "$lock" "$p50" "$p99"
done

printf '\nPilot complete.\n'
printf 'Selected CS_NS: %s\n' "$SELECTED_CS"
printf 'Pilot data: %s\n' "$OUT"
printf 'Next: run scripts/preflight.sh --final\n'
