import math

from src.common.models import MarketEvent, AssetSignal
from src.storage.market_signal_store import MarketSignalStore
from src.common.config import EWMA_ALPHA, SYNTHETIC_WORKLOAD_ITERATIONS

# ---------------------------------------------------------------------
# Market calculations
# ---------------------------------------------------------------------

def calculate_return(previous_price: float, new_price: float) -> float:
    """
    Calculate the return produced by the latest price update.
    """

    if previous_price <= 0:
        raise ValueError("previous_price must be greater than zero")

    return (new_price - previous_price) / previous_price


# ---------------------------------------------------------------------
# Synthetic model inference
# ---------------------------------------------------------------------

def run_synthetic_inference(event: MarketEvent, current_signal: AssetSignal, iterations: int = SYNTHETIC_WORKLOAD_ITERATIONS) -> float:
    """
    Perform a deterministic CPU workload representing model inference.

    The result is not used as a financial prediction. The calculation
    exists to create a repeatable computational workload that is kept
    constant across architectures.
    """

    value = (event.price * 0.001 + current_signal.expected_return + current_signal.risk)

    for i in range(iterations):
        value = (math.sin(value + (i % 100) * 0.0001) + math.cos(value * 0.5) + math.sqrt(abs(value) + 1.0))

    return value


# ---------------------------------------------------------------------
# Signal calculation
# ---------------------------------------------------------------------

def calculate_updated_signal(event: MarketEvent,current_signal: AssetSignal, alpha: float = EWMA_ALPHA) -> AssetSignal:
    """
    Calculate the updated expected return and risk for an asset.
    """

    latest_return = calculate_return(previous_price=current_signal.last_price, new_price=event.price,)

    # Exponentially weighted expected return.
    new_expected_return = ((1 - alpha) * current_signal.expected_return + alpha * latest_return)

    # Convert the previous risk value back into variance.
    previous_variance = current_signal.risk ** 2

    # Exponentially weighted variance.
    new_variance = ((1 - alpha) * previous_variance + alpha * (latest_return - current_signal.expected_return) ** 2)

    new_risk = math.sqrt(max(new_variance, 0.0))

    return AssetSignal(
        asset_id=event.asset_id,
        last_price=event.price,
        expected_return=new_expected_return,
        risk=new_risk,
        updated_at=event.timestamp,
    )


# ---------------------------------------------------------------------
# Main processor
# ---------------------------------------------------------------------

def process_market_event(event: MarketEvent, store: MarketSignalStore) -> AssetSignal:
    """
    Process one market event and update the asset's stored signal.
    """

    current_signal = store.get_signal(event.asset_id)

    if current_signal is None:
        raise KeyError(f"No existing signal found for {event.asset_id}")

    # Each asset should only be updated by newer market data.
    if event.timestamp <= current_signal.updated_at:
        raise ValueError(f"Market event for {event.asset_id} is not newer than the currently stored signal")

    # Represent the computation that would normally be performed
    # by the deployed asset-level model.
    run_synthetic_inference(event, current_signal)

    updated_signal = calculate_updated_signal(event, current_signal)
    store.update_signal(updated_signal)

    return updated_signal

"""
import time


def process_market_event(
    event: MarketEvent,
    store: MarketSignalStore,
) -> AssetSignal:

    start = time.perf_counter()

    current_signal = store.get_signal(event.asset_id)
    after_read = time.perf_counter()

    if current_signal is None:
        raise KeyError(
            f"No existing signal found for {event.asset_id}"
        )

    if event.timestamp <= current_signal.updated_at:
        raise ValueError(
            f"Market event for {event.asset_id} is not newer "
            f"than the currently stored signal"
        )

    run_synthetic_inference(
        event,
        current_signal,
    )
    after_inference = time.perf_counter()

    updated_signal = calculate_updated_signal(
        event,
        current_signal,
    )

    store.update_signal(updated_signal)
    after_write = time.perf_counter()

    print(
        f"read={(after_read - start) * 1000:.2f}ms | "
        f"inference={(after_inference - after_read) * 1000:.2f}ms | "
        f"write={(after_write - after_inference) * 1000:.2f}ms | "
        f"total={(after_write - start) * 1000:.2f}ms"
    )

    return updated_signal
"""