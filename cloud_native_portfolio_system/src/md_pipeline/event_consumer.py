import asyncio
import os
import socket
import time

import nats
from nats.errors import TimeoutError as NatsTimeoutError
from nats.js.api import AckPolicy, ConsumerConfig, DeliverPolicy

from src.common.config import (
    NATS_ACK_WAIT_SECONDS,
    NATS_CONNECT_TIMEOUT_SECONDS,
    NATS_CONSUMER,
    NATS_FETCH_BATCH_SIZE,
    NATS_FETCH_TIMEOUT_SECONDS,
    NATS_HEADER_CYCLE_START_NS,
    NATS_HEADER_PUBLISHED_AT_NS,
    NATS_MAX_ACK_PENDING,
    NATS_STREAM,
    NATS_SUBJECT,
    NATS_URL,
    SYNTHETIC_WORKLOAD_ITERATIONS,
    SYNTHETIC_WORKLOAD_PROFILE,
)
from src.common.models import MarketEvent
from src.md_pipeline.processor import process_market_event
from src.storage.market_signal_store import MarketSignalStore


# ---------------------------------------------------------------------
# Timing helpers
# ---------------------------------------------------------------------

def get_header_timestamp_ns(message, header_name: str) -> int | None:
    """
    Read a nanosecond timestamp from a NATS message header.
    """

    headers = message.header or {}

    value = headers.get(header_name)

    if value is None:
        return None

    return int(value)


def elapsed_ms(start_ns: int | None, end_ns: int) -> float | None:
    """
    Calculate elapsed wall-clock time in milliseconds.
    """

    if start_ns is None:
        return None

    return (end_ns - start_ns) / 1_000_000


# ---------------------------------------------------------------------
# Consumer
# ---------------------------------------------------------------------

async def run_consumer() -> None:
    worker_id = os.getenv("MD_CONSUMER_INSTANCE_ID", f"{socket.gethostname()}-{os.getpid()}")
    store = MarketSignalStore()

    if not store.check_connection():
        raise RuntimeError("Could not connect to the market signal store.")

    nc = await nats.connect(NATS_URL, connect_timeout=NATS_CONNECT_TIMEOUT_SECONDS)

    try:
        js = nc.jetstream()

        subscription = await js.pull_subscribe(
            subject=NATS_SUBJECT,
            durable=NATS_CONSUMER,
            stream=NATS_STREAM,
            config=ConsumerConfig(
                deliver_policy=DeliverPolicy.ALL,
                ack_policy=AckPolicy.EXPLICIT,
                ack_wait=NATS_ACK_WAIT_SECONDS,
                max_ack_pending=NATS_MAX_ACK_PENDING,
            ),
        )

        print("Market Data Event Consumer started")
        print(f"Worker: {worker_id}")
        print(f"NATS server: {NATS_URL}")
        print(f"Stream: {NATS_STREAM}")
        print(f"Subject: {NATS_SUBJECT}")
        print(f"Consumer: {NATS_CONSUMER}")
        print(f"Synthetic workload: {SYNTHETIC_WORKLOAD_PROFILE}")
        print(f"Synthetic iterations: {SYNTHETIC_WORKLOAD_ITERATIONS:,}")

        processed_count = 0

        while True:
            try:
                messages = await subscription.fetch(batch=NATS_FETCH_BATCH_SIZE, timeout=NATS_FETCH_TIMEOUT_SECONDS)

            except NatsTimeoutError:
                # No messages are currently waiting.
                continue

            for message in messages:
                try:
                    event = MarketEvent.model_validate_json(message.data)

                    # -------------------------------------------------
                    # Read timing headers
                    # -------------------------------------------------

                    cycle_started_at_ns = (get_header_timestamp_ns(message, NATS_HEADER_CYCLE_START_NS))
                    published_at_ns = (get_header_timestamp_ns(message,NATS_HEADER_PUBLISHED_AT_NS))

                    # -------------------------------------------------
                    # Process event
                    # -------------------------------------------------

                    processing_start = time.perf_counter()
                    process_market_event(event, store)
                    processing_latency_ms = (time.perf_counter() - processing_start) * 1000
                    completed_at_ns = time.time_ns()

                    signal_staleness_ms = elapsed_ms(cycle_started_at_ns, completed_at_ns)
                    event_update_latency_ms = elapsed_ms(published_at_ns, completed_at_ns)

                    # -------------------------------------------------
                    # ACK
                    # -------------------------------------------------

                    await message.ack()

                    processed_count += 1
                    # Only print once every 100 events.
                    if processed_count % 100 == 0:
                        print(f"Worker {worker_id} | Events processed: {processed_count:,} | Processing: {processing_latency_ms:.2f}ms | Event latency: {event_update_latency_ms:.2f}ms | Staleness: {signal_staleness_ms:.2f}ms")

                except (KeyError, ValueError) as error:
                    print(f"Rejected market event: {error}")
                    await message.term()

                except Exception as error:
                    print(f"Processing failed: {error}")
                    await message.nak()

    finally:
        await nc.close()


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main() -> None:
    try:
        asyncio.run(run_consumer())

    except KeyboardInterrupt:
        print("\nConsumer stopped.")


if __name__ == "__main__":
    main()