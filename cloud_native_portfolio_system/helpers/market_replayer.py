import argparse
import asyncio
from typing import Callable

import time
import nats
import numpy as np
import pandas as pd
import requests

from src.common.config import (
    DIRECT_API_TIMEOUT_SECONDS,
    DIRECT_API_URL,
    MARKET_TEST_SET_FILES,
    NATS_CONNECT_TIMEOUT_SECONDS,
    NATS_STREAM,
    NATS_SUBJECT,
    NATS_URL,
    VALID_DATASET_SIZES,
    NATS_CONSUMER,
    NATS_CYCLE_COMPLETION_TIMEOUT_SECONDS,
    NATS_CYCLE_POLL_INTERVAL_SECONDS,
    NATS_HEADER_CYCLE_START_NS,
    NATS_HEADER_PUBLISHED_AT_NS
)
from src.common.models import MarketEvent
from src.common.experiment_results import ExperimentRun


# ---------------------------------------------------------------------
# Dataset loading
# ---------------------------------------------------------------------

def load_market_events(dataset_size: str) -> pd.DataFrame:
    """
    Load one of the fixed market-data test sets.
    """

    if dataset_size not in VALID_DATASET_SIZES:
        raise ValueError(f"dataset_size must be one of: {', '.join(VALID_DATASET_SIZES)}")

    file_path = MARKET_TEST_SET_FILES[dataset_size]

    if not file_path.exists():
        raise FileNotFoundError(f"Market-data test set not found: {file_path}")

    return pd.read_csv(file_path, parse_dates=["timestamp"])


# ---------------------------------------------------------------------
# Direct HTTP sending
# ---------------------------------------------------------------------

def send_http(event: MarketEvent, session: requests.Session) -> None:
    """
    Send one market event to the direct-processing API.
    """

    response = session.post(DIRECT_API_URL, json=event.model_dump(mode="json"), timeout=DIRECT_API_TIMEOUT_SECONDS)
    response.raise_for_status()


# ---------------------------------------------------------------------
# Replayer
# ---------------------------------------------------------------------

class MarketReplayer:

    def __init__(self, dataset_size: str):
        self.dataset_size = dataset_size
        self.events = load_market_events(dataset_size)


    def get_grouped_events(self):
        """
        Return market events grouped by simulated update timestamp.
        """
        return self.events.groupby("timestamp", sort=False)


    # -----------------------------------------------------------------
    # Direct architecture
    # -----------------------------------------------------------------

    def replay_direct(self, send_event: Callable[[MarketEvent], None]) -> tuple[dict, list[dict], list[dict]]:
        """
        Replay all market events through the synchronous direct API.

        Returns summary metrics, cycle records and individual successful
        event latency measurements.
        """

        event_count = 0
        successful_count = 0
        cycle_count = 0
        error_count = 0

        event_latencies_ms = []
        cycle_records = []

        grouped_events = self.get_grouped_events()
        replay_start = time.perf_counter()

        for timestamp, period_events in grouped_events:
            cycle_count += 1
            cycle_event_count = 0

            cycle_start = time.perf_counter()
            print(f"\nStarting cycle {cycle_count}: {timestamp}")

            for _, row in period_events.iterrows():
                event = MarketEvent(asset_id=row["asset_id"], price=float(row["price"]), timestamp=timestamp.to_pydatetime())
                event_start = time.perf_counter()

                try:
                    send_event(event)
                    latency_ms = (time.perf_counter() - event_start) * 1000
                    event_latencies_ms.append(latency_ms)
                    successful_count += 1

                except requests.RequestException as error:
                    error_count += 1
                    print(f"Failed event {event.asset_id}: {error}")

                event_count += 1
                cycle_event_count += 1

            cycle_duration = (time.perf_counter() - cycle_start)
            cycle_records.append({"cycle": cycle_count, "cycle_timestamp": timestamp, "event_count": cycle_event_count, "duration_seconds": cycle_duration})

            print(f"Cycle complete: {timestamp} | {cycle_event_count:,} events | {cycle_duration:.3f}s")

        # -----------------------------------------------------------------
        # Summary
        # -----------------------------------------------------------------

        replay_duration = (time.perf_counter() - replay_start)
        error_rate = (error_count / event_count if event_count > 0 else 0.0)

        if event_latencies_ms:
            p50_latency_ms = float(np.percentile(event_latencies_ms, 50))
            p95_latency_ms = float(np.percentile(event_latencies_ms, 95))

        else:
            p50_latency_ms = None
            p95_latency_ms = None

        average_cycle_time = (float(np.mean([record["duration_seconds"] for record in cycle_records])) if cycle_records else None)

        metrics = {
            "cycles_completed": cycle_count,
            "events_attempted": event_count,
            "successful_events": successful_count,
            "failed_events": error_count,
            "error_rate": error_rate,
            "total_duration_seconds": replay_duration,
            "average_cycle_time_seconds": average_cycle_time,
            "p50_event_latency_ms": p50_latency_ms,
            "p95_event_latency_ms": p95_latency_ms,
        }

        # Create detailed records only AFTER the workload has completed.
        # This avoids constructing dictionaries during the processing path.
        latency_records = [{"event_number": index, "latency_ms": latency} for index, latency in enumerate(event_latencies_ms, start=1)]

        print("\nReplay complete")
        print(f"Cycles completed: {cycle_count:,}")
        print(f"Events sent: {event_count:,}")
        print(f"Errors: {error_count:,}")
        print(f"Total duration: {replay_duration:.3f}s")

        if p50_latency_ms is not None:
            print(f"p50 event latency: {p50_latency_ms:.2f} ms")
            print(f"p95 event latency: {p95_latency_ms:.2f} ms")

        if average_cycle_time is not None:
            print(f"Average cycle time: {average_cycle_time:.3f}s")

        return (metrics, cycle_records, latency_records)


    # -----------------------------------------------------------------
    # Event-driven architecture
    # -----------------------------------------------------------------

    async def wait_for_event_cycle_completion(self, status_subscription, cycle_number: int, timestamp, cycle_start: float, queue_records: list[dict]) -> None:
        """
        Wait until all events in the current update cycle have been
        processed and acknowledged.

        Consumer-state measurements are recorded using the same polling
        already required for cycle completion, avoiding a second
        monitoring loop.
        """

        wait_start = time.perf_counter()

        while True:
            consumer_info = (await status_subscription.consumer_info())
            pending = (consumer_info.num_pending or 0)
            ack_pending = (consumer_info.num_ack_pending or 0)

            # Record the consumer state while performing the existing
            # completion check.
            queue_records.append(
                {
                    "cycle": cycle_number,
                    "cycle_timestamp": timestamp,
                    "elapsed_seconds": time.perf_counter() - cycle_start,
                    "num_pending": pending,
                    "num_ack_pending": ack_pending,
                    "total_outstanding": pending + ack_pending,
                }
            )

            if (pending == 0 and ack_pending == 0):
                return

            elapsed = time.perf_counter() - wait_start

            if (elapsed > NATS_CYCLE_COMPLETION_TIMEOUT_SECONDS):
                raise TimeoutError(f"Timed out waiting for market update cycle {timestamp} to complete.\nPending: {pending}, awaiting acknowledgement: {ack_pending}")

            await asyncio.sleep(NATS_CYCLE_POLL_INTERVAL_SECONDS)

    async def replay_event_driven(self) -> tuple[dict, list[dict], list[dict]]:
        """
        Replay market events through NATS JetStream.

        Events belonging to one simulated update timestamp are published
        together. The next timestamp is not published until every event
        in the current cycle has been processed and acknowledged.

        Returns summary metrics, per-cycle records and sampled JetStream
        consumer backlog records.
        """

        nc = await nats.connect(NATS_URL, connect_timeout=NATS_CONNECT_TIMEOUT_SECONDS)

        try:
            js = nc.jetstream()

            status_subscription = (await js.pull_subscribe_bind(consumer=NATS_CONSUMER, stream=NATS_STREAM))

            event_count = 0
            cycle_count = 0

            cycle_records = []
            queue_records = []

            grouped_events = self.get_grouped_events()

            replay_start = time.perf_counter()

            # -------------------------------------------------------------
            # Replay each simulated market-data update cycle ONCE
            # -------------------------------------------------------------

            for timestamp, period_events in grouped_events:

                cycle_count += 1
                cycle_event_count = 0

                cycle_start = time.perf_counter()
                cycle_started_at_ns = time.time_ns()

                print(f"\nStarting cycle {cycle_count}: {timestamp}")

                # ---------------------------------------------------------
                # Publish current update cycle
                # ---------------------------------------------------------

                for _, row in period_events.iterrows():
                    event = MarketEvent(asset_id=row["asset_id"], price=float(row["price"]), timestamp=timestamp.to_pydatetime())

                    published_at_ns = time.time_ns()

                    await js.publish(
                        NATS_SUBJECT,
                        event.model_dump_json().encode(),
                        stream=NATS_STREAM,
                        headers={NATS_HEADER_CYCLE_START_NS: str(cycle_started_at_ns), NATS_HEADER_PUBLISHED_AT_NS: str(published_at_ns)}
                    )

                    event_count += 1
                    cycle_event_count += 1

                print(f"Published {cycle_event_count:,} events for cycle {timestamp}")

                # ---------------------------------------------------------
                # Wait until this cycle has completely processed
                # ---------------------------------------------------------

                await self.wait_for_event_cycle_completion(
                    status_subscription=status_subscription,
                    cycle_number=cycle_count,
                    timestamp=timestamp,
                    cycle_start=cycle_start,
                    queue_records=queue_records,
                )

                # ---------------------------------------------------------
                # Cycle complete
                # ---------------------------------------------------------

                cycle_duration = time.perf_counter() - cycle_start
                cycle_samples = [record for record in queue_records if record["cycle"] == cycle_count]

                peak_pending = max((record["num_pending"] for record in cycle_samples), default=0)
                peak_ack_pending = max((record["num_ack_pending"] for record in cycle_samples), default=0)
                peak_outstanding = max((record["total_outstanding"] for record in cycle_samples), default=0)

                cycle_records.append(
                    {
                        "cycle": cycle_count,
                        "cycle_timestamp": timestamp,
                        "event_count": cycle_event_count,
                        "duration_seconds": cycle_duration,
                        "peak_pending": peak_pending,
                        "peak_ack_pending": peak_ack_pending,
                        "peak_outstanding": peak_outstanding,
                    }
                )

                print(f"Cycle complete: {timestamp} | {cycle_event_count:,} events | {cycle_duration:.3f}s | peak outstanding: {peak_outstanding:,}")

            # -------------------------------------------------------------
            # Replay summary
            # -------------------------------------------------------------

            replay_duration = (time.perf_counter() - replay_start)
            average_cycle_time = (float(np.mean([record["duration_seconds"] for record in cycle_records])) if cycle_records else None)

            peak_queue_depth = max((record["total_outstanding"] for record in queue_records), default=0)
            peak_pending = max((record["num_pending"] for record in queue_records), default=0)
            peak_ack_pending = max((record["num_ack_pending"] for record in queue_records), default=0)

            metrics = {
                "cycles_completed": cycle_count,
                "events_published": event_count,
                "total_duration_seconds": replay_duration,
                "average_cycle_time_seconds": average_cycle_time,
                "peak_queue_depth": peak_queue_depth,
                "peak_pending": peak_pending,
                "peak_ack_pending": peak_ack_pending
            }

            print("\nReplay complete")
            print(f"Cycles completed: {cycle_count:,}")
            print(f"Events published: {event_count:,}")
            print(f"Total duration: {replay_duration:.3f}s")

            if average_cycle_time is not None:
                print(f"Average cycle time: {average_cycle_time:.3f}s")
            print(f"Peak queue depth: {peak_queue_depth:,}")

            return (metrics, cycle_records, queue_records)

        finally:
            await nc.close()


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------

def parse_args() -> argparse.Namespace:

    parser = argparse.ArgumentParser(description="Replay a fixed market-data experiment dataset through either the direct or event-driven architecture.")

    parser.add_argument("--dataset-size", required=True, choices=VALID_DATASET_SIZES, help="Market-data dataset to replay.")
    parser.add_argument("--architecture", required=True, choices=("direct", "event"), help="Architecture used for the replay.",)

    return parser.parse_args()


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main() -> None:

    args = parse_args()

    print(f"Dataset size: {args.dataset_size}")
    print(f"Architecture: {args.architecture}")

    replayer = MarketReplayer(args.dataset_size)

    # -----------------------------------------------------------------
    # Direct
    # -----------------------------------------------------------------

    if args.architecture == "direct":
        print(f"Direct API: {DIRECT_API_URL}")
        run = ExperimentRun(experiment="experiment_2_market_data", architecture="direct", metadata={"dataset_size": args.dataset_size,})

        try:
            with requests.Session() as session:
                (metrics, cycle_records, latency_records,) = replayer.replay_direct(lambda event: send_http(event, session))

            run.save_records(filename="cycles.csv", records=cycle_records)
            run.save_records(filename="event_latencies.csv", records=latency_records)
            run.complete(metrics=metrics)

            print(f"\nResults: {run.run_dir}")

        except Exception as error:
            run.complete(metrics={}, status="failed", error=str(error))
            raise

    # -----------------------------------------------------------------
    # Event driven
    # -----------------------------------------------------------------

    else:
        print(f"NATS server: {NATS_URL}")
        print(f"NATS stream: {NATS_STREAM}")
        print(f"NATS subject: {NATS_SUBJECT}")

        run = ExperimentRun(experiment="experiment_2_market_data", architecture="event", metadata={"dataset_size": args.dataset_size})

        try:
            (metrics, cycle_records, queue_records) = asyncio.run(replayer.replay_event_driven())

            run.save_records(filename="cycles.csv", records=cycle_records)
            run.save_records(filename="queue_samples.csv", records=queue_records)
            run.complete(metrics=metrics)

            print(f"\nResults: {run.run_dir}")

        except Exception as error:
            run.complete(metrics={}, status="failed", error=str(error))
            raise


if __name__ == "__main__":
    main()