#!/usr/bin/env bash

# Run the experiments

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG="$ROOT/config/experiment.conf"

if [ ! -f "$CONFIG" ]; then
    printf 'Experiment configuration not found: %s\n' "$CONFIG"
    exit 1
fi

source "$CONFIG"

TEST_ONE=0
TEST_MATRIX=0

if [ "${1:-}" = "--test-one" ]; then
    TEST_ONE=1
elif [ "${1:-}" = "--test-matrix" ]; then
    TEST_MATRIX=1
elif [ "$#" -gt 0 ]; then
    printf 'usage: %s [--test-one|--test-matrix]\n' "$0"
    exit 1
fi

# Get the benchmark path
if [[ "$BENCH_BIN" = /* ]]; then
    BENCH_PATH="$BENCH_BIN"
else
    BENCH_PATH="$ROOT/${BENCH_BIN#./}"
fi

# Check the main configuration - if any fails go back to past steps
if [ -z "$CPU_LIST" ]; then
    printf 'CPU_LIST has not been configured.\n'
    exit 1
fi

if [ -z "$PHYSICAL_CORES" ]; then
    printf 'PHYSICAL_CORES has not been configured.\n'
    exit 1
fi

if [ "$TEST_ONE" -eq 0 ] && [ "$TEST_MATRIX" -eq 0 ] && [ -z "$CS_NS" ]; then
    printf 'CS_NS has not been selected by the pilot.\n'
    exit 1
fi

if [ "$PHYSICAL_CORES" -lt 1 ]; then
    printf 'PHYSICAL_CORES must be at least 1.\n'
    exit 1
fi

# Use smaller values for quick tests
if [ "$TEST_ONE" -eq 1 ]; then
    RUN_CS_NS=500
    RUN_SAMPLES=10000
    RUN_WARMUP=100
    RUN_MODE="test-one"
elif [ "$TEST_MATRIX" -eq 1 ]; then
    RUN_CS_NS=500
    RUN_SAMPLES=2000
    RUN_WARMUP=50
    RUN_MODE="test-matrix"
else
    RUN_CS_NS="$CS_NS"
    RUN_SAMPLES="$TOTAL_SAMPLES"
    RUN_WARMUP="$WARMUP"
    RUN_MODE="final"
fi

# Build the thread counts up to C and 2C
THREAD_COUNTS=()
n=1

while [ "$n" -lt "$PHYSICAL_CORES" ]; do
    THREAD_COUNTS+=("$n")
    n=$((n * 2))
done

last_index=$((${#THREAD_COUNTS[@]} - 1))

if [ "${#THREAD_COUNTS[@]}" -eq 0 ] || [ "${THREAD_COUNTS[$last_index]}" -ne "$PHYSICAL_CORES" ]; then
    THREAD_COUNTS+=("$PHYSICAL_CORES")
fi

THREAD_COUNTS+=("$((PHYSICAL_CORES * 2))")

# Get the lock and CPU lists
read -ra LOCK_ARRAY <<< "$LOCKS"
IFS=',' read -ra CPU_ARRAY <<< "$CPU_LIST"

if [ "${#LOCK_ARRAY[@]}" -ne 3 ]; then
    printf 'Exactly three lock policies are required.\n'
    exit 1
fi

if [ "${#CPU_ARRAY[@]}" -ne "$PHYSICAL_CORES" ]; then
    printf 'CPU_LIST does not contain PHYSICAL_CORES CPUs.\n'
    exit 1
fi

# Final statistis
printf 'Lock Contention EVA Experiments\n'
printf '\nMeasurement CPUs: %s\n' "$CPU_LIST"
printf 'Physical cores: %s\n' "$PHYSICAL_CORES"
printf 'Mode: %s\n' "$RUN_MODE"
printf 'Critical section: %sns\n' "$RUN_CS_NS"
printf 'Samples: %s\n' "$RUN_SAMPLES"
printf 'Warm-up: %s\n' "$RUN_WARMUP"
printf 'Repeats: %s\n' "$REPEATS"
printf 'Locks: %s\n' "$LOCKS"
printf 'Thread counts: %s\n' "${THREAD_COUNTS[*]}"

# Compile the benchmark
printf '\nCompiling benchmark:\n'
gcc -O2 -Wall -Wextra -pthread -o "$BENCH_PATH" "$ROOT/lockbench.c"
printf 'Benchmark compiled.\n'

# Run the smoke test
printf '\nRunning smoke test:\n\n'

if "$ROOT/test_lockbench.sh" "$ROOT/lockbench.c" "$ROOT/lockbench_test"; then
    printf '\nSmoke test passed.\n'
else
    printf '\nSmoke test failed.\n'
    exit 1
fi

rm -f "$ROOT/lockbench_test"

# Run the final preflight
if [ "$RUN_MODE" = "final" ]; then
    printf '\nRunning final preflight...\n\n'

    if "$ROOT/scripts/preflight.sh" --final; then
        printf '\nFinal preflight passed.\n'
    else
        printf '\nFinal preflight failed.\n'
        printf 'Experiment stopped.\n'
        exit 1
    fi
fi

# Create the result directory
RUN_ID="$(date +%Y%m%d_%H%M%S)"

if [ "$TEST_ONE" -eq 1 ]; then
    FINAL_ROOT="$ROOT/$RESULTS_DIR/runner_test/$RUN_ID"
elif [ "$TEST_MATRIX" -eq 1 ]; then
    FINAL_ROOT="$ROOT/$RESULTS_DIR/runner_matrix_test/$RUN_ID"
else
    FINAL_ROOT="$ROOT/$RESULTS_DIR/final/$RUN_ID"
fi

if [ -e "$FINAL_ROOT" ]; then
    printf 'Result directory already exists: %s\n' "$FINAL_ROOT"
    exit 1
fi

mkdir -p "$FINAL_ROOT"
printf '\nResult directory: %s\n' "$FINAL_ROOT"

# Save the configuration and source
cp "$CONFIG" "$FINAL_ROOT/experiment.conf"
cp "$ROOT/lockbench.c" "$FINAL_ROOT/lockbench.c"
cp "$ROOT/scripts/run_experiments.sh" "$FINAL_ROOT/run_experiments.sh"

if [ "$TEST_ONE" -eq 1 ]; then
    TOTAL_RUNS=1
else
    TOTAL_RUNS=$((REPEATS * ${#THREAD_COUNTS[@]} * ${#LOCK_ARRAY[@]}))
fi

# Save the experiment metadata
{
    printf 'run_id=%s\n' "$RUN_ID"
    printf 'created_at=%s\n' "$(date --iso-8601=seconds)"
    printf 'hostname=%s\n' "$(hostname)"
    printf 'kernel=%s\n' "$(uname -r)"
    printf 'cpu_list=%s\n' "$CPU_LIST"
    printf 'physical_cores=%s\n' "$PHYSICAL_CORES"
    printf 'mode=%s\n' "$RUN_MODE"
    printf 'cs_ns=%s\n' "$RUN_CS_NS"
    printf 'samples=%s\n' "$RUN_SAMPLES"
    printf 'warmup=%s\n' "$RUN_WARMUP"
    printf 'repeats=%s\n' "$REPEATS"
    printf 'locks=%s\n' "$LOCKS"
    printf 'thread_counts=%s\n' "${THREAD_COUNTS[*]}"
    printf 'planned_configurations=%s\n' "$TOTAL_RUNS"
} > "$FINAL_ROOT/manifest.txt"

run_configuration() {
    local repeat=$1
    local n=$2
    local lock=$3
    local n_dir
    local run_dir
    local worker_map=""
    local samples_csv
    local stdout_txt
    local metadata_txt
    local validation_txt
    local expected_lines
    local actual_lines
    local expected_header
    local expected_cpu
    local valid=1
    local rc

    n_dir="$(printf 'n%03d' "$n")"
    run_dir="$FINAL_ROOT/$(printf 'repeat_%02d' "$repeat")/$n_dir/$lock"
    mkdir -p "$run_dir"

    samples_csv="$run_dir/samples.csv"
    stdout_txt="$run_dir/stdout.txt"
    metadata_txt="$run_dir/metadata.txt"
    validation_txt="$run_dir/validation.txt"

    # Map workers to CPUs
    for ((worker=0; worker<n; worker++)); do
        cpu="${CPU_ARRAY[$((worker % PHYSICAL_CORES))]}"
        worker_map="${worker_map}${worker_map:+,}${cpu}"
    done

    {
        printf 'mode=%s\n' "$RUN_MODE"
        printf 'repeat=%s\n' "$repeat"
        printf 'threads=%s\n' "$n"
        printf 'lock=%s\n' "$lock"
        printf 'cpu_list=%s\n' "$CPU_LIST"
        printf 'worker_cpus=%s\n' "$worker_map"
        printf 'cs_ns=%s\n' "$RUN_CS_NS"
        printf 'samples=%s\n' "$RUN_SAMPLES"
        printf 'warmup=%s\n' "$RUN_WARMUP"
        printf 'started_at=%s\n' "$(date --iso-8601=seconds)"
    } > "$metadata_txt"

    # Run the benchmark
    if "$BENCH_PATH" --lock "$lock" --threads "$n" --cpus "$CPU_LIST" --cs-ns "$RUN_CS_NS" --samples "$RUN_SAMPLES" --warmup "$RUN_WARMUP" --csv "$samples_csv" > "$stdout_txt" 2>&1; then
        printf 'benchmark_exit=0\n' >> "$metadata_txt"
    else
        rc=$?
        printf 'benchmark_exit=%s\n' "$rc" >> "$metadata_txt"
        printf 'FAIL benchmark exited with status %s\n' "$rc" > "$validation_txt"
        return 1
    fi

    # Validate the output
    : > "$validation_txt"

    realised="$(grep '^# cs:' "$stdout_txt" | sed -n 's/.*realised≈\([0-9]*\)ns.*/\1/p' || true)"
    timer="$(grep '^# timer:' "$stdout_txt" | sed -n 's/.*overhead≈\([0-9]*\)ns.*/\1/p' || true)"

    if [ -z "$realised" ] || [ -z "$timer" ]; then
        printf 'FAIL could not read calibration values\n' >> "$validation_txt"
        valid=0
    else
        printf 'realised_cs_ns=%s\n' "$realised" >> "$metadata_txt"
        printf 'timer_overhead_ns=%s\n' "$timer" >> "$metadata_txt"
    fi

    # Check the realised critical section
    if [ -n "$realised" ]; then
        lower=$((RUN_CS_NS * 80 / 100))
        upper=$((RUN_CS_NS * 120 / 100))

        if [ "$realised" -ge "$lower" ] && [ "$realised" -le "$upper" ]; then
            printf 'PASS realised CS: %sns\n' "$realised" >> "$validation_txt"
        elif [ "$RUN_MODE" = "final" ]; then
            printf 'FAIL realised CS %sns outside %s-%sns\n' "$realised" "$lower" "$upper" >> "$validation_txt"
            valid=0
        else
            printf 'WARN realised CS %sns outside %s-%sns\n' "$realised" "$lower" "$upper" >> "$validation_txt"
        fi
    fi

    # Check timer overhead
    if [ -n "$timer" ]; then
        minimum_cs=$((timer * 5))

        if [ "$RUN_CS_NS" -ge "$minimum_cs" ]; then
            printf 'PASS timer overhead: %sns\n' "$timer" >> "$validation_txt"
        elif [ "$RUN_MODE" = "final" ]; then
            printf 'FAIL CS %sns is less than 5x timer overhead %sns\n' "$RUN_CS_NS" "$timer" >> "$validation_txt"
            valid=0
        else
            printf 'WARN timer overhead check failed\n' >> "$validation_txt"
        fi
    fi

    expected_lines=$((RUN_SAMPLES + 1))
    actual_lines="$(wc -l < "$samples_csv")"

    if [ "$actual_lines" -eq "$expected_lines" ]; then
        printf 'PASS sample count: %s\n' "$RUN_SAMPLES" >> "$validation_txt"
    else
        printf 'FAIL expected %s CSV lines, found %s\n' "$expected_lines" "$actual_lines" >> "$validation_txt"
        valid=0
    fi

    expected_header="lock,threads,cs_ns,cs_realised_ns,thread_id,cpu_id,sample_idx,latency_ns"

    if [ "$(head -1 "$samples_csv")" = "$expected_header" ]; then
        printf 'PASS CSV schema\n' >> "$validation_txt"
    else
        printf 'FAIL CSV schema\n' >> "$validation_txt"
        valid=0
    fi

    if grep -q '^p50=' "$stdout_txt"; then
        printf 'PASS latency percentiles\n' >> "$validation_txt"
    else
        printf 'FAIL latency percentiles missing\n' >> "$validation_txt"
        valid=0
    fi

    if grep -q '# realised critical-section length:' "$stdout_txt"; then
        printf 'PASS realised CS output\n' >> "$validation_txt"
    else
        printf 'FAIL realised CS output missing\n' >> "$validation_txt"
        valid=0
    fi

    if grep -q "# calibration CPU: ${CPU_ARRAY[0]}" "$stdout_txt"; then
        printf 'PASS calibration CPU\n' >> "$validation_txt"
    else
        printf 'FAIL calibration CPU\n' >> "$validation_txt"
        valid=0
    fi

    # Check CSV values
    if awk -F, -v lock="$lock" -v threads="$n" -v cs="$RUN_CS_NS" 'NR > 1 && ($1 != lock || $2 != threads || $3 != cs) {exit 1}' "$samples_csv"; then
        printf 'PASS CSV configuration\n' >> "$validation_txt"
    else
        printf 'FAIL CSV configuration\n' >> "$validation_txt"
        valid=0
    fi

    # Check worker CPU placement
    for ((worker=0; worker<n; worker++)); do
        expected_cpu="${CPU_ARRAY[$((worker % PHYSICAL_CORES))]}"

        if grep -q "# thread $worker: cpu=$expected_cpu acquisitions=" "$stdout_txt"; then
            printf 'PASS worker %s CPU %s\n' "$worker" "$expected_cpu" >> "$validation_txt"
        else
            printf 'FAIL worker %s expected CPU %s\n' "$worker" "$expected_cpu" >> "$validation_txt"
            valid=0
        fi
    done

    # Record context switches
    total_vcsw="$(grep '^# thread ' "$stdout_txt" | sed -n 's/.* voluntary_ctxsw=\([0-9]*\) involuntary_ctxsw=.*/\1/p' | awk '{sum += $1} END {print sum + 0}')"
    total_ivcsw="$(grep '^# thread ' "$stdout_txt" | sed -n 's/.* involuntary_ctxsw=\([0-9]*\).*/\1/p' | awk '{sum += $1} END {print sum + 0}')"

    printf 'voluntary_ctxsw_total=%s\n' "$total_vcsw" >> "$metadata_txt"
    printf 'involuntary_ctxsw_total=%s\n' "$total_ivcsw" >> "$metadata_txt"
    printf 'INFO voluntary context switches: %s\n' "$total_vcsw" >> "$validation_txt"
    printf 'INFO involuntary context switches: %s\n' "$total_ivcsw" >> "$validation_txt"

    # Check spin preemption
    if [ "$lock" = "spin" ] && [ "$n" -le "$PHYSICAL_CORES" ]; then
        if [ "$total_ivcsw" -eq 0 ]; then
            printf 'PASS spin preemption check\n' >> "$validation_txt"
        else
            printf 'WARN spin run had %s involuntary context switches\n' "$total_ivcsw" >> "$validation_txt"
        fi
    fi

    printf 'finished_at=%s\n' "$(date --iso-8601=seconds)" >> "$metadata_txt"

    if [ "$valid" -ne 1 ]; then
        return 1
    fi

    return 0
}

# Run one small test
if [ "$TEST_ONE" -eq 1 ]; then
    TEST_N="${THREAD_COUNTS[0]}"
    TEST_LOCK="${LOCK_ARRAY[0]}"
    TEST_DIR="$FINAL_ROOT/repeat_01/$(printf 'n%03d' "$TEST_N")/$TEST_LOCK"

    printf '\nRunning one test: N=%s lock=%s\n' "$TEST_N" "$TEST_LOCK"

    if run_configuration 1 "$TEST_N" "$TEST_LOCK"; then
        cat "$TEST_DIR/validation.txt"
        printf '\nRunner test passed.\n'
        printf 'Test output: %s\n' "$TEST_DIR"
    else
        cat "$TEST_DIR/validation.txt"
        printf '\nRunner test failed.\n'
        printf 'Test output: %s\n' "$TEST_DIR"
        exit 1
    fi

# Run the full matrix
elif [ "$TEST_MATRIX" -eq 1 ] || [ "$RUN_MODE" = "final" ]; then
    if [ "$RUN_MODE" = "final" ]; then
        printf '\nRunning final experiment...\n'
    else
        printf '\nRunning matrix test...\n'
    fi

    COMPLETION="$FINAL_ROOT/completion.csv"
    printf 'run_number,repeat,threads,lock,status\n' > "$COMPLETION"
    MATRIX_RUN=0

    for ((repeat=1; repeat<=REPEATS; repeat++)); do
        offset=$(((repeat - 1) % ${#LOCK_ARRAY[@]}))
        LOCK_ORDER=()

        for ((i=0; i<${#LOCK_ARRAY[@]}; i++)); do
            index=$(((i + offset) % ${#LOCK_ARRAY[@]}))
            LOCK_ORDER+=("${LOCK_ARRAY[$index]}")
        done

        if (( repeat % 2 == 1 )); then
            N_ORDER=("${THREAD_COUNTS[@]}")
        else
            N_ORDER=()

            for ((i=${#THREAD_COUNTS[@]} - 1; i>=0; i--)); do
                N_ORDER+=("${THREAD_COUNTS[$i]}")
            done
        fi

        for n in "${N_ORDER[@]}"; do
            for lock in "${LOCK_ORDER[@]}"; do
                MATRIX_RUN=$((MATRIX_RUN + 1))
                printf '[%02d/%02d] repeat=%d N=%d lock=%s ... ' "$MATRIX_RUN" "$TOTAL_RUNS" "$repeat" "$n" "$lock"

                if run_configuration "$repeat" "$n" "$lock"; then
                    printf 'PASS\n'
                    printf '%s,%s,%s,%s,PASS\n' "$MATRIX_RUN" "$repeat" "$n" "$lock" >> "$COMPLETION"
                else
                    printf 'FAIL\n'
                    printf '%s,%s,%s,%s,FAIL\n' "$MATRIX_RUN" "$repeat" "$n" "$lock" >> "$COMPLETION"

                    if [ "$RUN_MODE" = "final" ]; then
                        printf '\nExperiment stopped after a failed run.\n'
                    else
                        printf '\nMatrix test stopped after a failed run.\n'
                    fi

                    exit 1
                fi
            done
        done
    done

    printf 'completed_configurations=%s\n' "$MATRIX_RUN" >> "$FINAL_ROOT/manifest.txt"
    printf 'completed_at=%s\n' "$(date --iso-8601=seconds)" >> "$FINAL_ROOT/manifest.txt"
    printf 'completion_status=PASS\n' >> "$FINAL_ROOT/manifest.txt"

    if [ "$RUN_MODE" = "final" ]; then
        printf '\nExperiment complete.\n'
    else
        printf '\nMatrix test passed.\n'
    fi

    printf 'Completed configurations: %s\n' "$MATRIX_RUN"
    printf 'Completion file: %s\n' "$COMPLETION"
fi
