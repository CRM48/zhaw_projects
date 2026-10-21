import argparse
import asyncio
import json
import time

import httpx
import numpy as np

from src.common.config import (
    EVALUATOR_REQUEST_FILE,
    EXPERIMENT_4_BURSTS,
    EXPERIMENT_4_BURST_CONCURRENCY,
    EXPERIMENT_4_BURST_REQUESTS,
    EXPERIMENT_4_IDLE_SECONDS,
    UR_API_TIMEOUT_SECONDS,
    UR_PORTFOLIO_EVALUATOR_URL
)
from src.common.experiment_results import ExperimentRun
from src.common.models import PortfolioEvaluationRequest



# ---------------------------------------------------------------------
# Payload
# ---------------------------------------------------------------------

def load_evaluator_request() -> dict:
    """
    Load and validate the fixed Experiment 4 evaluator request.
    """

    if not EVALUATOR_REQUEST_FILE.exists():
        raise FileNotFoundError(f"Experiment 4 request not found: {EVALUATOR_REQUEST_FILE}")

    with EVALUATOR_REQUEST_FILE.open("r", encoding="utf-8") as file:
        data = json.load(file)

    request = PortfolioEvaluationRequest.model_validate(data)
    return request.model_dump(mode="json")


# ---------------------------------------------------------------------
# Single evaluator request
# ---------------------------------------------------------------------

async def send_request(client: httpx.AsyncClient, url: str, payload: dict, burst_number: int, request_number: int, request_type: str) -> dict:
    """
    Send one evaluator request and record its end-to-end latency.
    """

    start = time.perf_counter()

    try:
        response = await client.post(url, json=payload)
        response.raise_for_status()

        latency_ms = (time.perf_counter() - start) * 1000

        return {
            "burst": burst_number,
            "request_number": request_number,
            "request_type": request_type,
            "success": True,
            "status_code": response.status_code,
            "latency_ms": latency_ms,
            "error": ""
        }

    except httpx.HTTPStatusError as error:
        latency_ms = (time.perf_counter() - start) * 1000
        return {
            "burst": burst_number,
            "request_number": request_number,
            "request_type": request_type,
            "success": False,
            "status_code": error.response.status_code,
            "latency_ms": latency_ms,
            "error": str(error)
        }

    except (httpx.TimeoutException, httpx.RequestError) as error:

        latency_ms = (time.perf_counter() - start) * 1000

        return {
            "burst": burst_number,
            "request_number": request_number,
            "request_type": request_type,
            "success": False,
            "status_code": None,
            "latency_ms": latency_ms,
            "error": str(error),
        }


# ---------------------------------------------------------------------
# Warm burst
# ---------------------------------------------------------------------

async def run_burst(client: httpx.AsyncClient, url: str, payload: dict, burst_number: int, request_count: int, concurrency: int) -> tuple[list[dict], float]:
    """
    Execute one fixed-size concurrent warm burst.
    """

    semaphore = asyncio.Semaphore(concurrency)

    async def limited_request(request_number: int,) -> dict:
        async with semaphore:
            return await send_request(client=client, url=url, payload=payload, burst_number=burst_number, request_number=request_number, request_type="warm")

    burst_start = time.perf_counter()
    tasks = [limited_request(request_number) for request_number in range(1, request_count + 1)]
    results = await asyncio.gather(*tasks)
    burst_duration = (time.perf_counter() - burst_start)

    return (results, burst_duration,)


# ---------------------------------------------------------------------
# Burst metrics
# ---------------------------------------------------------------------

def calculate_burst_metrics(burst_number: int, first_request: dict, warm_results: list[dict], burst_duration: float) -> dict:

    successful_warm = [result for result in warm_results if result["success"]]
    failed_warm = [result for result in warm_results if not result["success"]]

    if successful_warm:
        latencies = np.array([result["latency_ms"] for result in successful_warm])
        p50_latency = float(np.percentile(latencies, 50))
        p95_latency = float(np.percentile(latencies, 95))

    else:
        p50_latency = None
        p95_latency = None

    throughput = (len(successful_warm) / burst_duration if burst_duration > 0 else 0.0)
    error_rate = (len(failed_warm) / len(warm_results) if warm_results else 0.0)

    return {
        "burst": burst_number,
        "first_request_success": first_request["success"],
        "first_request_latency_ms": first_request["latency_ms"],
        "warm_requests": len(warm_results),
        "warm_successful_requests": len(successful_warm),
        "warm_failed_requests": len(failed_warm),
        "warm_error_rate": error_rate,
        "warm_burst_duration_seconds": burst_duration,
        "warm_throughput_requests_per_second": throughput,
        "warm_p50_latency_ms": p50_latency,
        "warm_p95_latency_ms": p95_latency,
    }


# ---------------------------------------------------------------------
# Experiment
# ---------------------------------------------------------------------

async def run_experiment(args: argparse.Namespace) -> None:

    payload = load_evaluator_request()

    run = ExperimentRun(
        experiment="experiment_4_serverless_suitability",
        architecture=args.deployment,
        metadata={
            "target_url": args.target_url,
            "deployment": args.deployment,
            "idle_seconds": args.idle_seconds,
            "bursts": args.bursts,
            "burst_requests": args.burst_requests,
            "burst_concurrency": args.concurrency,
        }
    )

    all_request_records = []
    burst_records = []

    limits = httpx.Limits(max_connections=args.concurrency, max_keepalive_connections=args.concurrency)

    try:
        async with httpx.AsyncClient(timeout=UR_API_TIMEOUT_SECONDS, limits=limits) as client:
            for burst_number in range(1, args.bursts + 1):

                # -----------------------------------------------------
                # Idle period
                # -----------------------------------------------------

                print(f"\nBurst {burst_number}")
                print(f"Idle for {args.idle_seconds:.1f}s...")

                await asyncio.sleep(args.idle_seconds)

                # -----------------------------------------------------
                # First request after idle
                # -----------------------------------------------------

                print("Sending first request after idle...")

                first_request = await send_request(
                    client=client,
                    url=args.target_url,
                    payload=payload,
                    burst_number=burst_number,
                    request_number=0,
                    request_type="first_after_idle",
                )

                all_request_records.append(first_request)

                print(f"First request latency: {first_request['latency_ms']:.2f} ms")

                # -----------------------------------------------------
                # Warm burst
                # -----------------------------------------------------

                print(f"Sending {args.burst_requests:,} warm requests at concurrency {args.concurrency}...")

                (warm_results,burst_duration) = await run_burst(
                    client=client,
                    url=args.target_url,
                    payload=payload,
                    burst_number=burst_number,
                    request_count=args.burst_requests,
                    concurrency=args.concurrency
                )

                all_request_records.extend(warm_results)

                burst_metrics = (calculate_burst_metrics(burst_number=burst_number, first_request=first_request, warm_results=warm_results, burst_duration=burst_duration))

                burst_records.append(burst_metrics)

                print(f"Warm burst duration: {burst_duration:.3f}s")
                print(f"Warm throughput: {burst_metrics['warm_throughput_requests_per_second']:.2f} requests/s")

                if (burst_metrics["warm_p50_latency_ms"] is not None):
                    print(f"Warm p50: {burst_metrics['warm_p50_latency_ms']:.2f} ms")
                    print(f"Warm p95: {burst_metrics['warm_p95_latency_ms']:.2f} ms")

        # -------------------------------------------------------------
        # Overall summary
        # -------------------------------------------------------------

        successful_records = [record for record in all_request_records if record["success"]]
        failed_records = [record for record in all_request_records if not record["success"]]
        first_request_latencies = [record["first_request_latency_ms"] for record in burst_records if record["first_request_success"]]
        warm_latencies = [record["latency_ms"] for record in all_request_records if (record["success"] and record["request_type"] == "warm")]

        metrics = {
            "total_requests": len(all_request_records),
            "successful_requests": len(successful_records),
            "failed_requests": len(failed_records),
            "error_rate": (len(failed_records) / len(all_request_records) if all_request_records else 0.0),
            "average_first_request_latency_ms": (float(np.mean(first_request_latencies)) if first_request_latencies else None),
            "overall_warm_p50_latency_ms": (float(np.percentile(warm_latencies, 50)) if warm_latencies else None),
            "overall_warm_p95_latency_ms": (float(np.percentile(warm_latencies, 95)) if warm_latencies else None)
        }

        # -------------------------------------------------------------
        # Save results
        # -------------------------------------------------------------

        run.save_records(filename="requests.csv", records=all_request_records)
        run.save_records(filename="bursts.csv", records=burst_records)
        run.complete(metrics=metrics)

        print("\nExperiment 4 workload complete")
        print(f"Run ID: {run.run_id}")
        print(f"Successful requests: {len(successful_records):,}")
        print(f"Failed requests: {len(failed_records):,}")

        if (metrics["average_first_request_latency_ms"] is not None):
            print(f"Average first-request latency: {metrics['average_first_request_latency_ms']:.2f} ms")

        if (metrics["overall_warm_p95_latency_ms"] is not None):
            print(f"Overall warm p95 latency: {metrics['overall_warm_p95_latency_ms']:.2f} ms")

        print(f"Results: {run.run_dir}")

    except Exception as error:
        run.complete(metrics={}, status="failed", error=str(error))
        raise


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate idle-to-burst workloads for Experiment 4.")

    parser.add_argument("--target-url", default=UR_PORTFOLIO_EVALUATOR_URL, help="Portfolio Evaluator endpoint.")
    parser.add_argument("--deployment", choices=("local", "always-running", "serverless"), default="local", help=("Deployment type recorded in experiment metadata."))
    parser.add_argument("--idle-seconds", type=float, default=EXPERIMENT_4_IDLE_SECONDS)
    parser.add_argument("--bursts", type=int, default=EXPERIMENT_4_BURSTS)
    parser.add_argument("--burst-requests", type=int, default=EXPERIMENT_4_BURST_REQUESTS)
    parser.add_argument("--concurrency", type=int, default=(EXPERIMENT_4_BURST_CONCURRENCY))

    return parser.parse_args()


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main() -> None:
    args = parse_args()
    if args.idle_seconds < 0:
        raise ValueError("idle-seconds cannot be negative")
    if args.bursts <= 0:
        raise ValueError("bursts must be greater than zero")
    if args.burst_requests <= 0:
        raise ValueError("burst-requests must be greater than zero")
    if args.concurrency <= 0:
        raise ValueError("concurrency must be greater than zero")

    asyncio.run(run_experiment(args))


if __name__ == "__main__":
    main()