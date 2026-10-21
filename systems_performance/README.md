# Lock Contention Experiment

A C-based systems performance experiment comparing the lock-acquisition latency of spinlocks, standard mutexes, and adaptive mutexes under different levels of contention.

The project investigates how different lock-waiting policies affect performance as the number of competing threads increases. It uses POSIX threads, CPU affinity, and controlled critical-section durations to measure lock-acquisition latency. The experiment includes automated system checks, calibration, and benchmarking scripts to support consistent measurements.

## Requirements

- Linux (tested with GCC and POSIX threads)
- GCC
- Bash
- Suitable CPU environment for reliable performance measurements

## Setup

1. Make the shell scripts executable:
`chmod +x scripts/*.sh test_lockbench.sh`

2. Collect the system information:
`./scripts/collect_sut.sh`

3. Configure the CPUs used for the experiment:
`./scripts/configure_experiment.sh`

4. Run the preflight checks:
`./scripts/preflight.sh`

## Pilot

Run the pilot to select the critical-section length:
`./scripts/run_pilot.sh`

This sets the critical-section length (`CS_NS`) in `config/experiment.conf`.

Run the final preflight check (optional, as it is also run automatically before the final experiment):
`./scripts/preflight.sh --final`

## Tests

Run a single configuration test:
`./scripts/run_experiments.sh --test-one`

Run the reduced experiment matrix:
`./scripts/run_experiments.sh --test-matrix`

## Final experiment

Run the full experiment with:
`./scripts/run_experiments.sh`

The final preflight checks are also run again automatically before the experiment starts.

Results are saved in the `results` directory.

If a final run stops because the realised critical-section length is outside the ±20% acceptance range, rerun the final experiment. Only use a complete result set where all configurations pass.
