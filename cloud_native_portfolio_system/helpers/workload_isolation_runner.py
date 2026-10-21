import argparse
import asyncio
import time

import requests

from helpers.market_replayer import MarketReplayer, send_http
from helpers.user_request_generator import execute_user_load_until_stop, load_user_requests
from src.common.config import (
    UR_COORDINATOR_URL,
    UR_MONOLITH_API_URL,
    USER_REQUEST_FILE,
    VALID_DATASET_SIZES
)
from src.common.experiment_results import ExperimentRun


# ---------------------------------------------------------------------
# User architecture
# ---------------------------------------------------------------------

def get_user_url(architecture: str) -> str:

    if architecture == "monolith":
        return UR_MONOLITH_API_URL

    return UR_COORDINATOR_URL


# ---------------------------------------------------------------------
# Direct market workload
# ---------------------------------------------------------------------

async def run_direct_market(replayer: MarketReplayer, start_event: asyncio.Event, stop_event: asyncio.Event):
    """
    Run the synchronous direct market replayer in a separate thread
    so it can execute concurrently with the asynchronous user load.
    """

    await start_event.wait()

    try:
        def execute():
            with requests.Session() as session:
                return replayer.replay_direct(lambda event: send_http(event, session))

        return await asyncio.to_thread(execute)

    finally:
        stop_event.set()


# ---------------------------------------------------------------------
# Event-driven market workload
# ---------------------------------------------------------------------

async def run_event_market(replayer: MarketReplayer, start_event: asyncio.Event, stop_event: asyncio.Event):
    """
    Run the asynchronous event-driven market workload.
    """

    await start_event.wait()

    try:
        return await (replayer.replay_event_driven())

    finally:
        stop_event.set()


# ---------------------------------------------------------------------
# No-market baseline
# ---------------------------------------------------------------------

async def run_no_market(duration_seconds: float, start_event: asyncio.Event, stop_event: asyncio.Event):
    """
    Hold the Experiment 3 user workload open for a fixed duration
    without running market processing.

    Provides a user-only baseline.
    """

    await start_event.wait()

    try:
        start = time.perf_counter()
        await asyncio.sleep(duration_seconds)
        duration = time.perf_counter() - start
        metrics = {"total_duration_seconds": duration}

        return (metrics, [], [])

    finally:
        stop_event.set()


# ---------------------------------------------------------------------
# Experiment
# ---------------------------------------------------------------------

async def run_experiment(args: argparse.Namespace) -> None:

    # -----------------------------------------------------------------
    # Load fixed user request pool
    # -----------------------------------------------------------------

    user_requests = load_user_requests(args.request_pool_size)
    user_url = get_user_url(args.user_architecture)

    # -----------------------------------------------------------------
    # Result run
    # -----------------------------------------------------------------

    architecture_name = (f"{args.user_architecture}_{args.market_architecture}_{args.resource_allocation}")

    run = ExperimentRun(
        experiment=("experiment_3_workload_isolation"),
        architecture=architecture_name,
        metadata={
            "user_architecture": args.user_architecture,
            "market_architecture": args.market_architecture,
            "market_dataset_size": args.market_dataset_size,
            "user_concurrency": args.user_concurrency,
            "request_pool_size": args.request_pool_size,
            "resource_allocation": args.resource_allocation,
        }
    )

    start_event = asyncio.Event()
    stop_event = asyncio.Event()

    # -----------------------------------------------------------------
    # User workload
    # -----------------------------------------------------------------

    user_task = asyncio.create_task(execute_user_load_until_stop(url=user_url, requests=user_requests, concurrency=args.user_concurrency, start_event=start_event, stop_event=stop_event))

    # -----------------------------------------------------------------
    # Market workload
    # -----------------------------------------------------------------

    if args.market_architecture == "none":
        market_task = asyncio.create_task(run_no_market(duration_seconds=(args.duration_seconds), start_event=start_event, stop_event=stop_event))

    else:
        replayer = MarketReplayer(args.market_dataset_size)

        if (args.market_architecture == "direct"):
            market_task = asyncio.create_task(run_direct_market(replayer=replayer, start_event=start_event, stop_event=stop_event))
        else:
            market_task = asyncio.create_task(run_event_market(replayer=replayer, start_event=start_event, stop_event=stop_event))

    # -----------------------------------------------------------------
    # Simultaneous start
    # -----------------------------------------------------------------

    print("\nExperiment 3 workloads ready.")
    print(f"User architecture: {args.user_architecture}")
    print(f"Market architecture: {args.market_architecture}")
    print(f"Market dataset: {args.market_dataset_size}")
    print(f"User concurrency: {args.user_concurrency}")
    print(f"Resource allocation: {args.resource_allocation}")

    combined_start = time.perf_counter()

    print("\nStarting workloads...\n")
    start_event.set()

    try:
        (user_result, market_result) = await asyncio.gather(user_task, market_task)
        (user_metrics, user_records) = user_result
        (market_metrics, market_cycle_records, market_detail_records) = market_result

        combined_duration = (time.perf_counter() - combined_start)

        # -------------------------------------------------------------
        # Save detailed records
        # -------------------------------------------------------------

        run.save_records(filename="user_requests.csv", records=user_records)

        if market_cycle_records:
            run.save_records(filename="market_cycles.csv", records=market_cycle_records)

        if market_detail_records:
            if (args.market_architecture == "direct"):
                market_detail_filename = ("market_event_latencies.csv")
            else:
                market_detail_filename = ("market_queue_samples.csv")

            run.save_records(filename=(market_detail_filename), records=(market_detail_records))

        # -------------------------------------------------------------
        # Combined result
        # -------------------------------------------------------------

        metrics = {"user": user_metrics, "market": market_metrics, "combined_duration_seconds": combined_duration}
        run.complete(metrics=metrics)

        # -------------------------------------------------------------
        # Console summary
        # -------------------------------------------------------------

        print("\nExperiment 3 complete")
        print(f"Run ID: {run.run_id}")
        print("\nUser workload:")
        print(f"Requests completed: {user_metrics['total_requests']:,}")
        print(f"Throughput: {user_metrics['throughput_requests_per_second']:.2f} requests/s")
        print(f"Error rate: {user_metrics['error_rate'] * 100:.2f}%")

        if (user_metrics["p50_latency_ms"] is not None):
            print(f"p50 latency: {user_metrics['p50_latency_ms']:.2f} ms")
            print(f"p95 latency: {user_metrics['p95_latency_ms']:.2f} ms")

        if (args.market_architecture != "none"):
            print("\nMarket workload:")
            print(f"Cycles completed: {market_metrics['cycles_completed']:,}")
            print(f"Average cycle time: {market_metrics['average_cycle_time_seconds']:.3f}s")

        print(f"\nResults: {run.run_dir}")

    except Exception as error:
        stop_event.set()
        run.complete(metrics={}, status="failed", error=str(error))
        raise


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------

def parse_args() -> argparse.Namespace:

    parser = argparse.ArgumentParser(description=("Run simultaneous user-request and market-data workloads for Experiment 3."))

    parser.add_argument("--user-architecture", required=True, choices=("monolith", "microservices"))
    parser.add_argument("--market-architecture", required=True, choices=("none", "direct", "event"))
    parser.add_argument("--market-dataset-size", choices=VALID_DATASET_SIZES, default="small",)
    parser.add_argument("--user-concurrency", type=int, default=5)
    parser.add_argument("--request-pool-size", type=int, default=10000)
    parser.add_argument("--duration-seconds", type=float, default=30.0, help=("Duration of the user-only baseline when --market-architecture none is used."))
    parser.add_argument("--resource-allocation", choices=("local-uncontrolled", "shared", "isolated"), default="local-uncontrolled", help=("Metadata describing the deployment's resource allocation."))

    return parser.parse_args()


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main() -> None:
    args = parse_args()
    asyncio.run(run_experiment(args))

if __name__ == "__main__":
    main()
