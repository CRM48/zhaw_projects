#!/usr/bin/env bash

# Simply collects system info for the Linux SUT

set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/results/sut"

if ! mkdir -p "$OUT"; then
    printf 'Could not create results/sut.\n' >&2
    exit 1
fi

printf 'Collecting SUT information:\n'
printf 'Results will be saved to: %s\n' "$OUT"


# General system information
uname -a > "$OUT/system.txt"
if [ -f /etc/os-release ]; then
    cat /etc/os-release >> "$OUT/system.txt"
fi

printf '\n' >> "$OUT/system.txt"
printf 'Kernel: %s\n' "$(uname -r)" >> "$OUT/system.txt"

if command -v ldd >/dev/null 2>&1; then
    ldd --version | head -1 >> "$OUT/system.txt"
else
    printf 'glibc: unavailable\n' >> "$OUT/system.txt"
fi

if command -v gcc >/dev/null 2>&1; then
    gcc --version | head -1 >> "$OUT/system.txt"
else
    printf 'gcc: unavailable\n' >> "$OUT/system.txt"
fi


# Get CPU information
if command -v lscpu >/dev/null 2>&1; then
    lscpu > "$OUT/cpu.txt"
    lscpu -e=CPU,CORE,SOCKET,NODE,ONLINE > "$OUT/topology.txt"
else
    printf 'lscpu unavailable\n' > "$OUT/cpu.txt"
    printf 'lscpu unavailable\n' > "$OUT/topology.txt"
fi

# Check for SMT / Hyper-Threading
{
    if [ -f /sys/devices/system/cpu/smt/control ]; then
        printf 'SMT control: %s\n' "$(cat /sys/devices/system/cpu/smt/control)"
    else
        printf 'SMT control: unavailable\n'
    fi

    if [ -f /sys/devices/system/cpu/smt/active ]; then
        printf 'SMT active: %s\n' "$(cat /sys/devices/system/cpu/smt/active)"
    else
        printf 'SMT active: unavailable\n'
    fi
} > "$OUT/smt.txt"


# Check for virtualisation
{
    if command -v systemd-detect-virt >/dev/null 2>&1; then
        virt="$(systemd-detect-virt 2>/dev/null || true)"
        [ -z "$virt" ] && virt="none"
        printf 'Virtualisation: %s\n' "$virt"
    else
        printf 'systemd-detect-virt unavailable\n'
    fi

    if command -v lscpu >/dev/null 2>&1; then
        lscpu | grep -Ei 'Hypervisor|Virtualization' || true
    fi

    if grep -qw hypervisor /proc/cpuinfo 2>/dev/null; then
        printf 'Hypervisor CPU flag: present\n'
    else
        printf 'Hypervisor CPU flag: absent\n'
    fi
} > "$OUT/virtualisation.txt"


# Get CPU governer/frequency info
{
    found=0
    for cpu in /sys/devices/system/cpu/cpu[0-9]*; do
        if [ -f "$cpu/cpufreq/scaling_governor" ]; then
            found=1

            id="${cpu##*cpu}"
            governor="$(cat "$cpu/cpufreq/scaling_governor")"
            min="$(cat "$cpu/cpufreq/scaling_min_freq" 2>/dev/null || printf 'unavailable\n')"
            max="$(cat "$cpu/cpufreq/scaling_max_freq" 2>/dev/null || printf 'unavailable\n')"

            printf 'CPU %s: governor=%s min=%s max=%s\n' "$id" "$governor" "$min" "$max"
        fi
    done

    if [ "$found" -eq 0 ]; then
        printf 'CPU frequency information unavailable\n'
    fi

    if command -v cpupower >/dev/null 2>&1; then
        printf '\n'
        cpupower frequency-info 2>/dev/null || true
    fi
} > "$OUT/frequency.txt"

printf '\nSUT information collected.\n'
printf 'Data stored in results/sut\n'
printf '\nNext: run scripts/configure_experiment.sh\n'
