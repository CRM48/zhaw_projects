import argparse
import asyncio
import time

import httpx
import numpy as np
import pandas as pd

from src.common.config import (
    UR_API_TIMEOUT_SECONDS,
    UR_COORDINATOR_URL,
    UR_LOAD_DEFAULT_CONCURRENCY,
    UR_LOAD_DEFAULT_REQUESTS,
    UR_MONOLITH_API_URL,
    USER_REQUEST_FILE,
    USER_ASSET_UNIVERSE_SIZE,
    USER_CANDIDATE_PORTFOLIOS,
    USER_PORTFOLIO_SIZE
)
from src.common.models import UserRequest
from src.common.experiment_results import ExperimentRun


# ---------------------------------------------------------------------
# Dataset loading
# ---------------------------------------------------------------------

def load_user_requests(request_count: int) -> list[UserRequest]:
    """
    Load a fixed number of requests from the deterministic user
    request dataset.
    """

    if not USER_REQUEST_FILE.exists():
        raise FileNotFoundError(f"User request dataset not found: {USER_REQUEST_FILE}")

    data = pd.read_csv(USER_REQUEST_FILE)

    if request_count <= 0:
        raise ValueError("request_count must be greater than zero")

    if request_count > len(data):
        raise ValueError(f"Requested {request_count:,} requests but dataset contains only {len(data):,}")

    requests = []

    for _, row in data.iloc[:request_count].iterrows():

        requests.append(
            UserRequest(
                request_id=row["request_id"],
                risk_tolerance=float(row["risk_tolerance"]),
                return_preference=float(row["return_preference"]),
                diversification_preference=float(row["diversification_preference"])
            )
        )

    return requests


# ---------------------------------------------------------------------
# Single request
# ---------------------------------------------------------------------

async def send_request(client: httpx.AsyncClient, semaphore: asyncio.Semaphore, url: str, request: UserRequest) -> dict:
    """
    Send one user request and record its end-to-end result.
    """

    async with semaphore:
        start = time.perf_counter()
        try:
            response = await client.post(url, json=request.model_dump(mode="json"))
            response.raise_for_status()

            latency_ms = (time.perf_counter() - start) * 1000

            return {"request_id": request.request_id, "success": True, "status_code": response.status_code, "latency_ms": latency_ms, "error": ""}

        except httpx.HTTPStatusError as error:
            latency_ms = (time.perf_counter() - start) * 1000

            return {"request_id":request.request_id, "success": False, "status_code": error.response.status_code, "latency_ms": latency_ms, "error": str(error)}

        except (httpx.TimeoutException, httpx.RequestError) as error:
            latency_ms = (time.perf_counter() - start) * 1000

            return {"request_id": request.request_id, "success": False, "status_code": None, "latency_ms": latency_ms, "error": str(error)}


async def execute_user_load_until_stop(url: str, requests: list[UserRequest], concurrency: int, start_event: asyncio.Event, stop_event: asyncio.Event) -> tuple[dict, list[dict]]:
    """
    Continuously send user requests at a fixed concurrency until the
    supplied stop event is set.

    Used by Experiment 3 so user requests remain active for the full
    duration of the simultaneous market-data workload.
    """

    if concurrency <= 0:
        raise ValueError("concurrency must be greater than zero")

    if not requests:
        raise ValueError("At least one user request is required")

    semaphore = asyncio.Semaphore(concurrency)

    limits = httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency)

    results = []

    next_request_index = 0
    next_request_number = 1

    async with httpx.AsyncClient(timeout=UR_API_TIMEOUT_SECONDS, limits=limits) as client:

        # -------------------------------------------------------------
        # Wait until both Experiment 3 workloads are ready
        # -------------------------------------------------------------

        await start_event.wait()
        workload_start = time.perf_counter()

        # -------------------------------------------------------------
        # Worker
        # -------------------------------------------------------------

        async def worker() -> None:

            nonlocal next_request_index
            nonlocal next_request_number

            while not stop_event.is_set():

                request = requests[next_request_index % len(requests)]

                request_number = next_request_number

                next_request_index += 1
                next_request_number += 1

                result = await send_request(client=client, semaphore=semaphore, url=url, request=request)

                result["request_number"] = request_number

                results.append(result)

        # -------------------------------------------------------------
        # Fixed number of concurrent workers
        # -------------------------------------------------------------

        workers = [asyncio.create_task(worker()) for _ in range(concurrency)]

        await asyncio.gather(*workers)

        workload_duration = (time.perf_counter() - workload_start)

    # -----------------------------------------------------------------
    # Metrics
    # -----------------------------------------------------------------

    successful_results = [result for result in results if result["success"]]
    failed_results = [result for result in results if not result["success"]]

    total_requests = len(results)
    successful_requests = len(successful_results)
    failed_requests = len(failed_results)

    throughput = (successful_requests / workload_duration if workload_duration > 0 else 0.0)
    error_rate = (failed_requests / total_requests if total_requests > 0 else 0.0)

    if successful_results:
        latencies_ms = np.array([result["latency_ms"] for result in successful_results])
        p50_latency_ms = float(np.percentile(latencies_ms, 50))
        p95_latency_ms = float(np.percentile(latencies_ms, 95))

    else:
        p50_latency_ms = None
        p95_latency_ms = None

    metrics = {
        "total_requests": total_requests,
        "successful_requests": successful_requests,
        "failed_requests": failed_requests,
        "error_rate": error_rate,
        "workload_duration_seconds": workload_duration,
        "throughput_requests_per_second": throughput,
        "p50_latency_ms": p50_latency_ms,
        "p95_latency_ms": p95_latency_ms,
    }

    return (metrics, results)


# ---------------------------------------------------------------------
# Load run
# ---------------------------------------------------------------------

async def run_load(architecture: str, url: str, requests: list[UserRequest], concurrency: int) -> None:
    """
    Execute one user-request workload and save experiment results.
    """

    if concurrency <= 0:
        raise ValueError("concurrency must be greater than zero")

    run = ExperimentRun(experiment="experiment_1_user_request", architecture=architecture,
        metadata={
            "target_url": url,
            "request_count": len(requests),
            "concurrency": concurrency,
            "asset_universe_size": USER_ASSET_UNIVERSE_SIZE,
            "portfolio_size": USER_PORTFOLIO_SIZE,
            "candidate_portfolios": USER_CANDIDATE_PORTFOLIOS,
        }
    )

    try:
        semaphore = asyncio.Semaphore(concurrency)
        limits = httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency)

        async with httpx.AsyncClient(timeout=UR_API_TIMEOUT_SECONDS, limits=limits) as client:
            workload_start = (time.perf_counter())
            tasks = [send_request(client=client, semaphore=semaphore, url=url, request=request) for request in requests]
            results = await asyncio.gather(*tasks)
            workload_duration = (time.perf_counter() - workload_start)

        successful_results = [result for result in results if result["success"]]
        failed_results = [result for result in results if not result["success"]]

        successful_requests = len(successful_results)
        failed_requests = len(failed_results)
        total_requests = len(results)

        throughput = (successful_requests / workload_duration if workload_duration > 0 else 0.0)
        error_rate = (failed_requests / total_requests if total_requests > 0 else 0.0)

        if successful_results:
            latencies_ms = np.array([result["latency_ms"] for result in successful_results])
            p50_latency_ms = float(np.percentile(latencies_ms, 50))
            p95_latency_ms = float(np.percentile(latencies_ms, 95))

        else:
            p50_latency_ms = None
            p95_latency_ms = None

        metrics = {
            "total_requests": total_requests,
            "successful_requests": successful_requests,
            "failed_requests": failed_requests,
            "error_rate": error_rate,
            "workload_duration_seconds": workload_duration,
            "throughput_requests_per_second": throughput,
            "p50_latency_ms": p50_latency_ms,
            "p95_latency_ms": p95_latency_ms
        }

        run.save_records(filename="requests.csv", records=results)
        run.complete(metrics=metrics)

        print("\nRun complete")
        print(f"Run ID: {run.run_id}")

        print(f"\nTotal requests: {total_requests:,}")
        print(f"Successful requests: {successful_requests:,}")
        print(f"Failed requests: {failed_requests:,}")

        print(f"\nTotal duration: {workload_duration:.3f}s")
        print(f"Throughput: {throughput:.2f} requests/s")
        print(f"Error rate: {error_rate * 100:.2f}%")

        if p50_latency_ms is not None:
            print(f"\np50 latency: {p50_latency_ms:.2f} ms")
            print(f"p95 latency: {p95_latency_ms:.2f} ms")

        print(f"\nResults: {run.run_dir}")

    except Exception as error:
        run.complete(metrics={}, status="failed", error=str(error))

        raise

# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------

def parse_args() -> argparse.Namespace:

    parser = argparse.ArgumentParser(description="Generate controlled user-request workloads for the monolith or microservice architecture.")

    parser.add_argument("--architecture", required=True, choices=("monolith", "microservices"), help="Architecture to test.")
    parser.add_argument("--requests", type=int, default=UR_LOAD_DEFAULT_REQUESTS, help="Number of requests to send.")
    parser.add_argument("--concurrency", type=int, default=UR_LOAD_DEFAULT_CONCURRENCY, help="Maximum number of requests simultaneously in flight.")

    return parser.parse_args()


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main() -> None:

    args = parse_args()

    if args.architecture == "monolith":
        url = UR_MONOLITH_API_URL
    else:
        url = UR_COORDINATOR_URL

    requests = load_user_requests(args.requests)

    print(f"Architecture: {args.architecture}")
    print(f"Target: {url}")
    print(f"Requests: {args.requests:,}")

    print(f"Concurrency: {args.concurrency}")

    asyncio.run(run_load(architecture=args.architecture, url=url, requests=requests, concurrency=args.concurrency))


if __name__ == "__main__":
    main()