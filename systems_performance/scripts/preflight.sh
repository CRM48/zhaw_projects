#!/usr/bin/env bash

# Check the Linux SUT before running the experiment

set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SUT="$ROOT/results/sut"
CONFIG="$ROOT/config/experiment.conf"

FINAL_MODE=0

if [ "${1:-}" = "--final" ]; then
    FINAL_MODE=1
elif [ "$#" -gt 0 ]; then
    printf 'usage: %s [--final]\n' "$0"
    exit 2
fi

FAIL=0
WARN=0

pass() {
    printf 'PASS  %s\n' "$1"
}

warn() {
    printf 'WARN  %s\n' "$1"
    WARN=$((WARN + 1))
}

fail() {
    printf 'FAIL  %s\n' "$1"
    FAIL=$((FAIL + 1))
}

# Return success if a CPU is inside a Linux CPU list such as 0-3,8-11
cpu_is_allowed() {
    local needle=$1
    local list=$2
    local part start end
    local -a parts

    IFS=',' read -ra parts <<< "$list"

    for part in "${parts[@]}"; do
        if [[ "$part" == *-* ]]; then
            start="${part%-*}"
            end="${part#*-}"

            if [ "$needle" -ge "$start" ] &&
               [ "$needle" -le "$end" ]; then
                return 0
            fi
        elif [ "$needle" -eq "$part" ]; then
            return 0
        fi
    done

    return 1
}

if [ ! -d "$SUT" ]; then
    printf 'No SUT information found.\n'
    printf 'Run scripts/collect_sut.sh first.\n'
    exit 1
fi

if [ ! -f "$CONFIG" ]; then
    printf 'Experiment configuration not found: %s\n' "$CONFIG"
    exit 1
fi

source "$CONFIG"

CPU_LIST="${CPU_LIST:-}"
PHYSICAL_CORES="${PHYSICAL_CORES:-}"
CS_NS="${CS_NS:-}"

CPU_ARRAY=()

if [ -n "$CPU_LIST" ]; then
    IFS=',' read -ra CPU_ARRAY <<< "$CPU_LIST"
fi

printf 'Lock Contention EVA - SUT preflight\n'

if [ "$FINAL_MODE" -eq 1 ]; then
    printf 'Mode: FINAL\n'
else
    printf 'Mode: setup\n'
fi

# Linux
if uname -s | grep -q '^Linux$'; then
    pass "Linux detected"
else
    fail "Machine is not running Linux"
fi

# glibc
if ldd --version 2>&1 | head -1 | grep -Eqi 'glibc|GNU libc'; then
    pass "glibc detected"
else
    fail "glibc not detected - adaptive mutex arm requires glibc"
fi

# gcc
if command -v gcc >/dev/null 2>&1; then
    pass "gcc available"
else
    fail "gcc missing"
fi

# lscpu
if command -v lscpu >/dev/null 2>&1; then
    pass "lscpu available"
else
    fail "lscpu missing"
fi

# Check for virtualisation
virt="unknown"

if command -v systemd-detect-virt >/dev/null 2>&1; then
    virt="$(systemd-detect-virt 2>/dev/null || true)"
    [ -z "$virt" ] && virt="none"
fi

if [ "$virt" = "none" ]; then
    pass "No virtualisation detected"
elif [ "$virt" = "unknown" ]; then
    fail "Could not confirm that the machine is bare metal"
else
    fail "Virtualised environment detected: $virt"
fi

# Check physical cores
cores="$(lscpu -p=CORE,SOCKET 2>/dev/null |
    grep -v '^#' |
    sort -u |
    wc -l)"

if [ "$cores" -ge 2 ]; then
    pass "$cores physical cores detected"
else
    fail "Fewer than two physical cores detected"
fi

# Check confgured measurement CPUs
if [ -z "$CPU_LIST" ] || [ -z "$PHYSICAL_CORES" ]; then
    if [ "$FINAL_MODE" -eq 1 ]; then
        fail "CPU_LIST or PHYSICAL_CORES has not been configured"
    else
        warn "Measurement CPUs have not been configured yet"
    fi
else
    if [ "${#CPU_ARRAY[@]}" -eq "$PHYSICAL_CORES" ]; then
        pass "Configured $PHYSICAL_CORES measurement CPUs"
    else
        fail "CPU_LIST does not contain PHYSICAL_CORES CPUs"
    fi

    allowed="$(awk '/^Cpus_allowed_list:/ {print $2}' /proc/self/status)"
    cpu_list_ok=1

    for cpu in "${CPU_ARRAY[@]}"; do
        if ! cpu_is_allowed "$cpu" "$allowed"; then
            fail "Configured CPU $cpu is not in the process allowed CPU set"
            cpu_list_ok=0
        fi
    done

    if [ "$cpu_list_ok" -eq 1 ]; then
        pass "All configured measurement CPUs are allowed"
    fi

    declare -A SEEN_CORES=()

    SOCKET_REF=""
    topology_ok=1

    for cpu in "${CPU_ARRAY[@]}"; do
        topo="$(
            lscpu -p=CPU,CORE,SOCKET,ONLINE 2>/dev/null |
            awk -F',' -v cpu="$cpu" '
                !/^#/ && $1 == cpu {
                    print $2 "," $3 "," $4
                    exit
                }
            '
        )"

        if [ -z "$topo" ]; then
            fail "Could not determine topology for configured CPU $cpu"
            topology_ok=0
            continue
        fi

        IFS=',' read -r core socket online <<< "$topo"

        if [ "${online^^}" != "Y" ]; then
            fail "Configured CPU $cpu is offline"
            topology_ok=0
        fi

        key="$socket:$core"

        if [ -n "${SEEN_CORES[$key]+x}" ]; then
            fail "More than one configured CPU belongs to physical core $core on socket $socket"
            topology_ok=0
        else
            SEEN_CORES["$key"]=1
        fi

        if [ -z "$SOCKET_REF" ]; then
            SOCKET_REF="$socket"
        elif [ "$socket" != "$SOCKET_REF" ]; then
            fail "Configured measurement CPUs span multiple sockets"
            topology_ok=0
        fi
    done

    if [ "$topology_ok" -eq 1 ]; then
        pass "Measurement CPUs use distinct physical cores on one socket"
    fi
fi

# Check SMT / Hyper-Threading
if [ -f /sys/devices/system/cpu/smt/active ]; then
    smt="$(cat /sys/devices/system/cpu/smt/active)"

    if [ "$smt" = "0" ]; then
        pass "SMT disabled"
    elif [ "$FINAL_MODE" -eq 1 ]; then
        fail "SMT is enabled"
    else
        warn "SMT is enabled - disable before the final experiment"
    fi
else
    if [ "$FINAL_MODE" -eq 1 ]; then
        fail "SMT state could not be determined"
    else
        warn "SMT state could not be determined"
    fi
fi

# Check CPU governor
governors=""
governor_missing=0

if [ "${#CPU_ARRAY[@]}" -gt 0 ]; then
    for cpu in "${CPU_ARRAY[@]}"; do
        governor_file="/sys/devices/system/cpu/cpu${cpu}/cpufreq/scaling_governor"

        if [ -f "$governor_file" ]; then
            governors="${governors}$(cat "$governor_file")"$'\n'
        else
            governor_missing=1
        fi
    done
else
    for governor_file in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
        if [ -f "$governor_file" ]; then
            governors="${governors}$(cat "$governor_file")"$'\n'
        fi
    done
fi

unique_governors="$(
    printf '%s\n' "$governors" |
    sed '/^$/d' |
    sort -u |
    paste -sd, -
)"

if [ "$governor_missing" -eq 1 ] || [ -z "$unique_governors" ]; then
    if [ "$FINAL_MODE" -eq 1 ]; then
        fail "CPU governor state unavailable on one or more measurement CPUs"
    else
        warn "CPU governor information unavailable"
    fi
elif [ "$unique_governors" = "performance" ]; then
    pass "Measurement CPU governor is performance"
else
    if [ "$FINAL_MODE" -eq 1 ]; then
        fail "Measurement CPU governor is not performance: $unique_governors"
    else
        warn "Measurement CPU governor is not performance: $unique_governors"
    fi
fi

# Check turbo/boost
BOOST_STATE="unknown"
BOOST_SOURCE=""

if [ -f /sys/devices/system/cpu/intel_pstate/no_turbo ]; then
    BOOST_SOURCE="intel_pstate/no_turbo"

    if [ "$(cat /sys/devices/system/cpu/intel_pstate/no_turbo)" = "1" ]; then
        BOOST_STATE="disabled"
    else
        BOOST_STATE="enabled"
    fi
elif [ -f /sys/devices/system/cpu/cpufreq/boost ]; then
    BOOST_SOURCE="cpufreq/boost"

    if [ "$(cat /sys/devices/system/cpu/cpufreq/boost)" = "0" ]; then
        BOOST_STATE="disabled"
    else
        BOOST_STATE="enabled"
    fi
fi

if [ "$BOOST_STATE" = "disabled" ]; then
    pass "CPU turbo/boost disabled ($BOOST_SOURCE)"
elif [ "$BOOST_STATE" = "enabled" ]; then
    if [ "$FINAL_MODE" -eq 1 ]; then
        fail "CPU turbo/boost is enabled ($BOOST_SOURCE)"
    else
        warn "CPU turbo/boost is enabled - disable before final experiment"
    fi
else
    if [ "$FINAL_MODE" -eq 1 ]; then
        fail "CPU turbo/boost state could not be determined"
    else
        warn "CPU turbo/boost state could not be determined"
    fi
fi

# Check optional validation tools
for tool in perf mpstat pidstat numactl; do
    if command -v "$tool" >/dev/null 2>&1; then
        pass "$tool available"
    else
        warn "$tool missing"
    fi
done

# Check that the pilot selected a CS value
if [ "$FINAL_MODE" -eq 1 ]; then
    if [ -z "$CS_NS" ]; then
        fail "CS_NS has not been selected by the pilot"
    else
        pass "CS_NS set to ${CS_NS}ns"
    fi

    if [ -f "$ROOT/results/pilot/pilot_summary.csv" ]; then
        pass "Pilot summary exists"
    else
        fail "Pilot summary not found"
    fi
fi

# Benchmark smoke test
printf '\nRunning benchmark smoke test...\n'

if [ -x "$ROOT/test_lockbench.sh" ]; then
    if "$ROOT/test_lockbench.sh" \
        "$ROOT/lockbench.c" \
        "$ROOT/lockbench_test" \
        >/dev/null 2>&1; then

        pass "lockbench functional tests passed"
    else
        fail "lockbench functional tests failed"
    fi
else
    fail "test_lockbench.sh not found or not executable"
fi

rm -f "$ROOT/lockbench_test"

printf '\nPreflight complete: %s failure(s), %s warning(s).\n' "$FAIL" "$WARN"

if [ "$FAIL" -gt 0 ]; then
    if [ "$FINAL_MODE" -eq 1 ]; then
        printf 'Machine is not ready for final data collection.\n'
    else
        printf 'Machine is not ready for the experiment.\n'
    fi

    exit 1
fi

if [ "$WARN" -gt 0 ]; then
    if [ "$FINAL_MODE" -eq 1 ]; then
        printf 'Final checks passed with warnings.\n'
    else
        printf 'Setup can continue, but review the warnings.\n'
    fi
else
    if [ "$FINAL_MODE" -eq 1 ]; then
        printf 'Machine is ready for final data collection.\n'
    else
        printf 'Machine is ready to continue.\n'
    fi
fi

if [ "$FINAL_MODE" -eq 1 ]; then
    printf 'Next: run scripts/run_experiments.sh\n'
else
    printf 'Next: run scripts/run_pilot.sh\n'
fi
