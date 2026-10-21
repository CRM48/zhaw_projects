#!/usr/bin/env bash

# Selects suitable measurement CPUs from the curent SUT - one logical CPU per physical core

set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SUT="$ROOT/results/sut"
CONFIG="$ROOT/config/experiment.conf"

if [ ! -d "$SUT" ]; then
    printf 'SUT information not found.\n'
    printf 'Run scripts/collect_sut.sh first.\n'
    exit 1
fi

if [ ! -f "$CONFIG" ]; then
    printf 'Experiment configuration not found: %s\n' "$CONFIG"
    exit 1
fi

if ! command -v lscpu >/dev/null 2>&1; then
    printf 'lscpu is required to configure the experiment.\n'
    exit 1
fi

ALLOWED="$(awk '/^Cpus_allowed_list:/ {print $2}' /proc/self/status)"

if [ -z "$ALLOWED" ]; then
    printf 'Could not determine the process allowed CPU set.\n'
    exit 1
fi

ALLOWED_CPUS=""

IFS=',' read -ra PARTS <<< "$ALLOWED"

for part in "${PARTS[@]}"; do
    if [[ "$part" == *-* ]]; then
        start="${part%-*}"
        end="${part#*-}"
        for ((cpu=start; cpu<=end; cpu++)); do
            ALLOWED_CPUS="${ALLOWED_CPUS}${ALLOWED_CPUS:+,}${cpu}"
        done
    else
        ALLOWED_CPUS="${ALLOWED_CPUS}${ALLOWED_CPUS:+,}${part}"
    fi
done

# Select the first socket containing an online CPU that this process can use
SOCKET="$(
    lscpu -p=CPU,CORE,SOCKET,ONLINE |
    awk -F',' -v allowed="$ALLOWED_CPUS" '
        BEGIN {
            n = split(allowed, cpus, ",")
            for (i = 1; i <= n; i++)
                permitted[cpus[i]] = 1
        }

        !/^#/ && toupper($4) == "Y" && permitted[$1] {
            print $3
            exit
        }
    '
)"

if [ -z "$SOCKET" ]; then
    printf 'Could not determine a usable CPU socket.\n'
    exit 1
fi

# Select one allowed logical CPU from each physical core on that socket
CPU_LIST="$(
    lscpu -p=CPU,CORE,SOCKET,ONLINE |
    awk -F',' -v socket="$SOCKET" -v allowed="$ALLOWED_CPUS" '
        BEGIN {
            n = split(allowed, cpus, ",")
            for (i = 1; i <= n; i++)
                permitted[cpus[i]] = 1
        }

        !/^#/ && toupper($4) == "Y" && $3 == socket && permitted[$1] {
            key = $2 ":" $3

            if (!seen[key]++)
                print $1
        }
    ' |
    paste -sd, -
)"

if [ -z "$CPU_LIST" ]; then
    printf 'Could not select measurement CPUs.\n'
    exit 1
fi

CORE_COUNT="$(printf '%s\n' "$CPU_LIST" | awk -F',' '{print NF}')"

printf 'Process allowed CPUs: %s\n' "$ALLOWED"
printf 'Detected socket: %s\n' "$SOCKET"
printf 'Physical cores available on socket: %s\n' "$CORE_COUNT"
printf 'One logical CPU per core: %s\n' "$CPU_LIST"

# Reserve the first physical core for OS/background work if at least three cores exist
if [ "$CORE_COUNT" -ge 3 ]; then
    HOUSEKEEPING_CPU="${CPU_LIST%%,*}"
    CPU_LIST="${CPU_LIST#*,}"
    PHYSICAL_CORES=$((CORE_COUNT - 1))
    printf '\nReserving CPU %s for system/background activity.\n' "$HOUSEKEEPING_CPU"

else
    PHYSICAL_CORES="$CORE_COUNT"
    printf '\nOnly %s physical cores available - no core reserved for housekeeping.\n' "$CORE_COUNT"
fi

printf '\nMeasurement CPU list: %s\n' "$CPU_LIST"
printf 'Usable physical cores: %s\n' "$PHYSICAL_CORES"

sed -i "s/^CPU_LIST=.*/CPU_LIST=\"$CPU_LIST\"/" "$CONFIG"
sed -i "s/^PHYSICAL_CORES=.*/PHYSICAL_CORES=\"$PHYSICAL_CORES\"/" "$CONFIG"

printf '\nUpdated config/experiment.conf\n'
printf 'CPU_LIST="%s"\n' "$CPU_LIST"
printf 'PHYSICAL_CORES="%s"\n' "$PHYSICAL_CORES"
printf '\nNext: run scripts/preflight.sh\n'
